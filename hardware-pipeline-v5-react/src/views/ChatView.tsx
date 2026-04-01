import { useState, useRef, useEffect, useCallback, memo } from 'react';
import { Project, PhaseMeta } from '../types';
import { api } from '../api';
import { ensureMermaid, purgeMermaidScratch, nextMermaidId } from '../utils/mermaid';

export interface ChatMessage { role: 'user' | 'ai'; text: string; }

/** Sanitise AI-generated Mermaid code */
function sanitizeMermaid(raw: string): string {
  let code = raw.trim().replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  // Normalise graph → flowchart
  code = code.replace(/^graph\s+(TD|LR|TB|RL|BT)/im, 'flowchart $1');
  // Step 0: join lines where [ is opened but not closed on the same line.
  // LLMs sometimes split a node label across multiple lines with a real newline,
  // e.g.  SINK[Heatsink\n  AIR["Ambient Air"]  which becomes two lines in the file.
  // The "end" keyword on the next line then causes a parser crash.
  {
    const joinedLines: string[] = [];
    for (const line of code.split('\n')) {
      if (joinedLines.length > 0) {
        const last = joinedLines[joinedLines.length - 1];
        const opens = (last.match(/\[/g) || []).length;
        const closes = (last.match(/\]/g) || []).length;
        if (opens > closes) {
          joinedLines[joinedLines.length - 1] = last.trimEnd() + ' ' + line.trimStart();
          continue;
        }
      }
      joinedLines.push(line);
    }
    code = joinedLines.join('\n');
  }
  // Ensure known diagram type on line 1
  const first = code.split('\n')[0].trim().toLowerCase();
  const known = ['flowchart', 'sequencediagram', 'classdiagram', 'statediagram',
    'erdiagram', 'gantt', 'pie', 'gitgraph', 'mindmap', 'timeline'];
  if (!known.some(t => first.startsWith(t))) code = 'flowchart TD\n' + code;
  // Strip HTML tags (except <br/>) inside labels
  code = code.replace(/<(?!br\s*\/?)[^>]+>/gi, ' ');
  // Replace literal \n escape sequences (backslash + n) with a space.
  // LLMs often emit \n inside node labels thinking it's a newline escape.
  code = code.replace(/\\n/g, ' ');
  // Sanitize flowchart node labels: [ ... ], ( ... ), { ... }
  // Replace & and angle brackets that break the parser
  const sanitizeLabel = (inner: string) =>
    inner
      .replace(/&(?!amp;|lt;|gt;|#)/g, 'and')
      .replace(/</g, 'lt ')
      .replace(/>/g, ' gt');
  code = code.replace(/\[([^\]]*)\]/g, (_m, inner: string) => `[${sanitizeLabel(inner)}]`);
  code = code.replace(/\(([^)]*)\)/g, (_m, inner: string) => `(${sanitizeLabel(inner)})`);
  code = code.replace(/\{([^}]*)\}/g, (_m, inner: string) => `{${sanitizeLabel(inner)}}`);
  // Sanitize state diagram transition labels (after '-->...:'): remove > < and extra colons
  // e.g.  STATE --> FAULT : VSWR > 10:1  →  STATE --> FAULT : VSWR gt 10,1
  if (first.startsWith('statediagram')) {
    code = code.split('\n').map(line => {
      // Match lines with a state transition label:  ... --> ... : label
      const m = line.match(/^(\s*.*?-->\s*\S+\s*:)(.*)$/);
      if (m) {
        const label = m[2]
          .replace(/>/g, ' gt ')
          .replace(/</g, ' lt ')
          .replace(/:/g, ',');
        return m[1] + label;
      }
      return line;
    }).join('\n');
  }
  return code;
}

function MermaidBlock({ code, color }: { code: string; color: string }) {
  const [svg, setSvg] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const idRef = useRef(nextMermaidId());

  useEffect(() => {
    let cancelled = false;
    setSvg(null);
    setError(false);

    const safeCode = sanitizeMermaid(code);
    const id = idRef.current;

    ensureMermaid(() => {
      if (cancelled) return;

      (async () => {
        try {
          // render() only — no parse() to avoid Mermaid firing error toasts before our catch
          const result = await window.mermaid!.render(id, safeCode);
          const svgStr: string = result?.svg ?? '';
          purgeMermaidScratch(id);
          if (cancelled) return;
          if (svgStr.includes('<svg') && !svgStr.includes('Syntax error') && !svgStr.includes('class="error"')) {
            setSvg(svgStr);
          } else {
            setError(true);
          }
        } catch {
          purgeMermaidScratch(id);
          if (!cancelled) setError(true);
        }
      })();
    });

    return () => {
      cancelled = true;
      purgeMermaidScratch(id);
    };
  }, [code]);

  if (!svg) {
    return (
      <div style={{ margin: '10px 0' }}>
        <div style={{
          fontSize: 10, color, letterSpacing: '0.08em',
          background: `${color}0d`, padding: '4px 12px',
          borderRadius: '6px 6px 0 0', border: `1px solid ${color}22`,
          borderBottom: 'none',
        }}>
          {error ? 'BLOCK DIAGRAM (source)' : 'BLOCK DIAGRAM \u2014 rendering...'}
        </div>
        <pre style={{
          background: 'var(--panel2)', border: `1px solid ${color}22`,
          borderRadius: '0 0 6px 6px', padding: '12px 14px', margin: 0,
          fontSize: 12, color, fontFamily: "'JetBrains Mono',monospace",
          overflowX: 'auto', lineHeight: 1.65, whiteSpace: 'pre-wrap',
        }}>
          {code}
        </pre>
      </div>
    );
  }

  return (
    <div style={{ margin: '10px 0' }}>
      <div style={{
        fontSize: 10, color, letterSpacing: '0.08em',
        background: `${color}0d`, padding: '4px 12px',
        borderRadius: '6px 6px 0 0', border: `1px solid ${color}22`,
        borderBottom: 'none', display: 'flex', alignItems: 'center', gap: 6,
      }}>
        &#128202; SYSTEM ARCHITECTURE DIAGRAM
      </div>
      <div style={{
        background: 'var(--panel2)', border: `1px solid ${color}22`,
        borderRadius: '0 0 6px 6px', padding: '16px', overflowX: 'auto',
      }}
        dangerouslySetInnerHTML={{ __html: svg }}
      />
    </div>
  );
}


// ---- Lightweight markdown renderer with Mermaid diagram support ----

function renderMarkdown(text: string, color: string): React.ReactNode {
  const lines = text.split('\n');
  const elements: React.ReactNode[] = [];
  let i = 0;

  const inline = (raw: string): React.ReactNode => {
    const parts = raw.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g);
    return parts.map((p, j) => {
      if (p.startsWith('**') && p.endsWith('**'))
        return <strong key={j} style={{ color: 'var(--text)', fontWeight: 700 }}>{p.slice(2,-2)}</strong>;
      if (p.startsWith('*') && p.endsWith('*'))
        return <em key={j} style={{ color: 'var(--text2)', fontStyle: 'italic' }}>{p.slice(1,-1)}</em>;
      if (p.startsWith('`') && p.endsWith('`'))
        return <code key={j} style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 11, background: 'var(--panel2)', color, padding: '1px 5px', borderRadius: 3 }}>{p.slice(1,-1)}</code>;
      return p;
    });
  };

  while (i < lines.length) {
    const line = lines[i];

    // Headers
    if (line.startsWith('### ')) {
      elements.push(<div key={i} style={{ fontSize: 13, fontWeight: 700, color, margin: '12px 0 4px' }}>{inline(line.slice(4))}</div>);
      i++; continue;
    }
    if (line.startsWith('## ')) {
      elements.push(<div key={i} style={{ fontFamily:"'Syne',sans-serif", fontSize: 14, fontWeight: 800, color: 'var(--text)', margin: '14px 0 6px' }}>{inline(line.slice(3))}</div>);
      i++; continue;
    }
    if (line.startsWith('# ')) {
      elements.push(<div key={i} style={{ fontFamily:"'Syne',sans-serif", fontSize: 16, fontWeight: 800, color: 'var(--text)', margin: '16px 0 8px', borderBottom: `1px solid ${color}33`, paddingBottom: 6 }}>{inline(line.slice(2))}</div>);
      i++; continue;
    }

    // Code blocks — Mermaid gets rendered as diagrams, others as styled code
    if (line.startsWith('```')) {
      const lang = line.slice(3).trim();
      const isMermaid = lang.toLowerCase() === 'mermaid';
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith('```')) { codeLines.push(lines[i]); i++; }
      const codeText = codeLines.join('\n');

      if (isMermaid) {
        elements.push(<MermaidBlock key={`mermaid-${i}`} code={codeText} color={color} />);
      } else {
        elements.push(
          <div key={`code-${i}`} style={{ margin: '10px 0' }}>
            <pre style={{
              background: 'var(--panel2)',
              border: '1px solid var(--border2)',
              borderRadius: 6,
              padding: '12px 14px', margin: 0,
              fontSize: 12, color: 'var(--text2)',
              fontFamily: "'JetBrains Mono',monospace",
              overflowX: 'auto', lineHeight: 1.65, whiteSpace: 'pre-wrap',
            }}>
              {codeText}
            </pre>
          </div>
        );
      }
      if (i < lines.length) i++;
      continue;
    }

    // Table
    if (line.startsWith('|')) {
      const tableLines: string[] = [];
      while (i < lines.length && lines[i].startsWith('|')) { tableLines.push(lines[i]); i++; }
      const rows = tableLines.filter(l => !l.match(/^\|[-| :]+\|$/));
      elements.push(
        <div key={`tbl-${i}`} style={{ overflowX: 'auto', margin: '10px 0' }}>
          <table style={{ borderCollapse: 'collapse', fontSize: 12, width: '100%' }}>
            <tbody>
              {rows.map((row, ri) => {
                const cells = row.split('|').slice(1, -1);
                return (
                  <tr key={ri} style={{ borderBottom: `1px solid ${color}22` }}>
                    {cells.map((cell, ci) => (
                      <td key={ci} style={{ padding: '6px 12px', color: ri === 0 ? color : 'var(--text2)', fontWeight: ri === 0 ? 600 : 400, background: ri === 0 ? `${color}0d` : 'transparent', fontFamily: "'DM Mono',monospace", borderRight: `1px solid ${color}11` }}>
                        {inline(cell.trim())}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      );
      continue;
    }

    // Bullet list
    if (line.startsWith('- ') || line.startsWith('* ')) {
      const items: string[] = [];
      while (i < lines.length && (lines[i].startsWith('- ') || lines[i].startsWith('* '))) { items.push(lines[i].slice(2)); i++; }
      elements.push(
        <ul key={`ul-${i}`} style={{ margin: '6px 0', padding: 0, listStyle: 'none' }}>
          {items.map((item, j) => (
            <li key={j} style={{ display: 'flex', gap: 8, alignItems: 'flex-start', marginBottom: 4 }}>
              <span style={{ color, marginTop: 3, fontSize: 9, flexShrink: 0 }}>&#9679;</span>
              <span style={{ fontSize: 13, color: 'var(--text2)', lineHeight: 1.55 }}>{inline(item)}</span>
            </li>
          ))}
        </ul>
      );
      continue;
    }

    // Blank line
    if (!line.trim()) { elements.push(<div key={i} style={{ height: 6 }} />); i++; continue; }

    // Paragraph
    elements.push(<div key={i} style={{ fontSize: 13, color: 'var(--text2)', lineHeight: 1.65, marginBottom: 2 }}>{inline(line)}</div>);
    i++;
  }
  return <>{elements}</>;
}

// ---- Memoized message row — skips re-render when only `streaming` state changes ----
const ChatMessageItem = memo(function ChatMessageItem({ msg, color }: { msg: ChatMessage; color: string }) {
  if (msg.role === 'user') {
    return (
      <div style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <div style={{ maxWidth: '75%', padding: '10px 15px', borderRadius: 8, background: `${color}18`, border: `1px solid ${color}33`, fontSize: 13, color: 'var(--text)', lineHeight: 1.6, fontFamily: "'DM Mono',monospace", whiteSpace: 'pre-wrap' }}>
            {msg.text}
          </div>
        </div>
      </div>
    );
  }
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ padding: '14px 18px', borderRadius: 8, background: 'var(--panel2)', border: '1px solid var(--panel3)' }}>
        <div style={{ fontSize: 10, color, marginBottom: 8, letterSpacing: '0.1em' }}>AI RESPONSE</div>
        {renderMarkdown(msg.text, color)}
      </div>
    </div>
  );
});

// ── QuickReplyPanel ───────────────────────────────────────────────────────────
// Parses the last AI message for numbered questions and renders as a modal
// popup with clickable chips + an "Other..." option per question.

interface ParsedQuestion {
  index: number;       // 1-based question number
  label: string;       // short label e.g. "Supply voltage"
  body: string;        // full question text
  options: string[];   // extracted answer chips (empty = show only Other)
}

/**
 * Split a question body containing multiple independent questions into sub-cards.
 * Only splits on "? " followed by common English question-starter words so that
 * inline option lists like "A, B, or C?" are never broken apart.
 */
function splitMultiBody(q: ParsedQuestion): ParsedQuestion[] {
  if ((q.body.match(/\?/g) || []).length < 2) return [q];

  // Only split before recognised question-opener words (not mid-option-list)
  const parts = q.body.split(
    /\?\s+(?=(?:Do|Does|Did|Is|Are|Was|Were|Will|Would|Can|Could|Should|Have|Has|What|Which|How|Where|When|Who|Please|Specify|Indicate|Select)\b)/
  );
  if (parts.length <= 1) return [q];

  return parts
    .map(p => p.trim())
    .filter(p => p.length > 5)
    .map(part => {
      const body = part.endsWith('?') || part.endsWith('!') ? part : part + '?';
      return { ...q, body, options: extractOptions(body) };
    });
}

/** Expand multi-sentence questions and renumber the whole list 1, 2, 3… */
function expandAndRenumber(questions: ParsedQuestion[]): ParsedQuestion[] {
  const expanded: ParsedQuestion[] = [];
  for (const q of questions) expanded.push(...splitMultiBody(q));
  return expanded.map((q, i) => ({ ...q, index: i + 1 }));
}

function parseQuestionsFromText(text: string): ParsedQuestion[] {

  // Helper: strip leading em-dash / dash that AIs emit after the label separator
  // e.g. "**Label** — body" → body captured as "— body" → we strip to "body"
  const stripLeadingDash = (s: string) => s.replace(/^[—–\-]\s+/, '').trim();

  // ── Format A: "1. **Label**: body?" — label + body on same line ──────────
  {
    const questions: ParsedQuestion[] = [];
    const lineRe = /^(\d+)\.\s+\*{0,2}([^:*\n]{2,50})\*{0,2}[:\s]+(.+)$/gm;
    let m: RegExpExecArray | null;
    while ((m = lineRe.exec(text)) !== null) {
      const idx = parseInt(m[1]);
      const label = m[2].trim();
      const body = stripLeadingDash(m[3]);
      questions.push({ index: idx, label, body, options: extractOptions(body) });
    }
    if (questions.length > 0) return expandAndRenumber(questions);
  }

  // ── Format B: numbered section headers + bullet points underneath ─────────
  // e.g.:  "1. **Application**\n• What is this driving?\n• Temp range?"
  {
    const questions: ParsedQuestion[] = [];
    const lines = text.split('\n');
    let sectionLabel = '';
    let qIdx = 0;

    for (const line of lines) {
      // Section header: "1. **Label**" or "1. Label" (no colon body after)
      const secM = line.match(/^\d+\.\s+\*{0,2}([^*\n:]{2,60})\*{0,2}\s*$/);
      if (secM) { sectionLabel = secM[1].trim(); continue; }

      // Bullet line under a section
      if (sectionLabel) {
        const bulletM = line.match(/^\s*[•\-\*]\s+(.+)$/);
        if (bulletM) {
          qIdx++;
          const body = stripLeadingDash(bulletM[1]);
          questions.push({ index: qIdx, label: sectionLabel, body, options: extractOptions(body) });
        }
      }
    }
    if (questions.length > 0) return expandAndRenumber(questions);
  }

  // ── Format C: standalone bold header + numbered questions below ───────────
  // e.g.:  "**Power & Performance:**\n1. What is the max current?\n2. What frequency?"
  {
    const questions: ParsedQuestion[] = [];
    const lines = text.split('\n');
    let sectionLabel = '';

    for (const line of lines) {
      // Standalone bold-only line: "**Section Header:**" or "**Section Header**"
      const boldM = line.match(/^\s*\*{2}([^*\n]{2,60})\*{2}:?\s*$/);
      if (boldM) {
        sectionLabel = boldM[1].replace(/:$/, '').trim();
        continue;
      }
      // Numbered question under a bold header (plain "1. question?" — no inline label)
      if (sectionLabel) {
        const numM = line.match(/^\s*(\d+)\.\s+(.+)$/);
        if (numM) {
          const body = stripLeadingDash(numM[2]);
          questions.push({ index: parseInt(numM[1]), label: sectionLabel, body, options: extractOptions(body) });
        }
        // Blank line between sections — reset so next bold header wins
        else if (line.trim() === '' && questions.length > 0) {
          sectionLabel = '';
        }
      }
    }
    if (questions.length > 0) return expandAndRenumber(questions);
  }

  // ── Format D: plain numbered questions "1. question?" — no labels ─────────
  // Fallback: catch any remaining "1. some question?" patterns
  {
    const questions: ParsedQuestion[] = [];
    const plainRe = /^(\d+)\.\s+(.{10,200}[?!])\s*$/gm;
    let dm: RegExpExecArray | null;
    while ((dm = plainRe.exec(text)) !== null) {
      const idx = parseInt(dm[1]);
      const body = stripLeadingDash(dm[2]);
      // Derive a short label from the first 4 words of the question
      const words = body.replace(/[?!.]/g, '').split(/\s+/);
      const label = words.slice(0, 4).join(' ');
      questions.push({ index: idx, label, body, options: extractOptions(body) });
    }
    if (questions.length > 0) return expandAndRenumber(questions);
  }

  return [];
}

function extractOptions(body: string): string[] {
  // ── Normalise chip text ────────────────────────────────────────────────────
  // Strip leading "— " / "– " / "- " that the AI adds after the label separator
  const cleanBody = body.replace(/^[—–\-]\s+/, '').trim();

  // Normalise a single chip: strip leading "or"/"and" and common articles,
  // then capitalise first letter so chips look consistent.
  const normalizeChip = (s: string): string => {
    let t = s.trim()
      .replace(/^(or|and)\s+/i, '')
      .replace(/^(a|an|the|just|only)\s+/i, '')
      .trim();
    return t.length > 0 ? t.charAt(0).toUpperCase() + t.slice(1) : t;
  };

  // Word-count check after normalization (articles stripped → fairer count)
  const chipWords = (s: string) => normalizeChip(s).split(/\s+/).length;
  const shortWords = (parts: string[]) => parts.every(p => chipWords(p) <= 4);

  // ── Domain shortcuts (high-confidence, checked first) ──────────────────────

  // Temperature / grade — triggered either by keyword OR by grade terms in the options
  const tempKeyword = /\b(temperature|thermal|operating\s+temp|temp\s+range|grade)\b/i.test(cleanBody);
  const tempGrades  = /\b(commercial|industrial|automotive|mil.?spec|military)\b/i.test(cleanBody) &&
                      /(-\d+|°[CF]|ambient|outdoor)/i.test(cleanBody);
  if (tempKeyword || tempGrades) {
    const chips: string[] = [];
    if (/commercial/i.test(cleanBody))          chips.push('Commercial (0–70°C)');
    if (/industrial/i.test(cleanBody))          chips.push('Industrial (−40–85°C)');
    if (/automotive/i.test(cleanBody))          chips.push('Automotive (−40–105°C)');
    if (/mil.?spec|military/i.test(cleanBody))  chips.push('MIL-SPEC (−55–125°C)');
    if (chips.length >= 2) return chips;
    return ['Commercial (0–70°C)', 'Industrial (−40–85°C)', 'Automotive (−40–105°C)', 'MIL-SPEC (−55–125°C)'];
  }

  // Cooling / thermal management
  if (/\b(forced\s+air|natural\s+convect|conduction.cool|heatsink|heat\s*sink)\b/i.test(cleanBody)) {
    return ['Forced air (fan)', 'Natural convection', 'Conduction-cooled', 'Custom/TBD'];
  }

  // ── Strip ALL parentheticals for end-of-sentence option scanning ───────────
  // e.g. "CAN (CANopen/J1939?), UART" → "CAN, UART"
  // e.g. "(or expected gain range)? A 10W..." → "? A 10W..."
  const bodyClean = cleanBody.replace(/\s*\([^)]*\)/g, '').replace(/\s+/g, ' ').trim();

  // Focus on the last clause after a colon or em-dash intro
  const lastClause = bodyClean.split(/[:\u2014\u2013]/).pop()?.trim() ?? bodyClean;

  // "A, B, or C?" / "A or B?" anchored to end of sentence
  const endOrRe = /\b(\w[\w\s/\-]{0,28})(?:,\s*\w[\w\s/\-]{0,28})*(?:,?\s*or\s+\w[\w\s/\-]{0,28})\s*[?!.]?\s*$/i;
  const endM = lastClause.match(endOrRe);
  if (endM) {
    const raw = endM[0].replace(/[?!.]\s*$/, '').trim();
    const parts = raw
      .split(/,\s*(?:or\s+)?|\s+or\s+/)
      .map(s => normalizeChip(s))
      .filter(s => s.length > 1 && s.length < 40);
    if (parts.length >= 2 && shortWords(parts)) return parts.slice(0, 5);
  }

  // ── "e.g." / "i.e." parentheticals ONLY — avoids pulling in inline parens ──
  // Only match explicit example lists, NOT parenthetical notes like (overtemp, VSWR)
  const egParens = Array.from(cleanBody.matchAll(/\(\s*(?:e\.g\.|i\.e\.)[.,]?\s*([^)]{4,120})\)/gi));
  for (const pm of egParens) {
    const inner = pm[1].replace(/^(?:e\.g\.|i\.e\.)[.,]?\s*/i, '');
    const parts = inner
      .split(/[,/]/)
      .map(s => normalizeChip(s))
      .filter(s => s.length > 1 && s.length < 32);
    if (parts.length >= 2 && shortWords(parts)) return parts.slice(0, 5);
  }

  // ── "whether X or Y" ───────────────────────────────────────────────────────
  const whetherM = cleanBody.match(/whether\s+(?:you\s+(?:can|need|should|want|prefer)\s+)?(.{3,35}?)\s+or\s+(?:need\s+|use\s+)?(.{3,35}?)(?:\?|$|\s*\()/i);
  if (whetherM) {
    const a = normalizeChip(whetherM[1]);
    const b = normalizeChip(whetherM[2]);
    if (shortWords([a, b]) && a.length > 2 && b.length > 2) return [a, b];
  }

  // ── Yes / No (only when there's no "or" offering other choices) ────────────
  if (/\?/.test(cleanBody) && !/\bor\b/i.test(cleanBody) &&
      /\b(do you|is there|are there|will|should|does|can you|have you|is it|would you)\b/i.test(cleanBody)) {
    return ['Yes', 'No'];
  }

  return [];
}

// Single question card inside the popup
function QuestionCard({
  q, color, selected, onSelect,
}: {
  q: ParsedQuestion;
  color: string;
  selected: string;
  onSelect: (val: string) => void;
}) {
  const [otherOpen, setOtherOpen] = useState(false);
  const [otherText, setOtherText] = useState('');

  const isOtherSelected = selected.startsWith('__other__:');
  const otherValue = isOtherSelected ? selected.slice(10) : otherText;

  const toggleOther = () => {
    if (otherOpen) {
      setOtherOpen(false);
      if (isOtherSelected) onSelect('');
    } else {
      setOtherOpen(true);
      onSelect('');
    }
  };

  const commitOther = (val: string) => {
    setOtherText(val);
    if (val.trim()) onSelect('__other__:' + val.trim());
    else onSelect('');
  };

  return (
    <div style={{
      background: 'var(--panel)', border: `1px solid ${color}22`,
      borderRadius: 8, padding: '12px 14px',
    }}>
      <div style={{ fontSize: 11, color, fontFamily: "'DM Mono',monospace", letterSpacing: '0.06em', marginBottom: 4 }}>
        Q{q.index}
      </div>
      <div style={{ fontSize: 12.5, color: 'var(--text)', marginBottom: 10, lineHeight: 1.5 }}>
        {q.body}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        {q.options.map(opt => {
          const isSel = selected === opt;
          return (
            <button key={opt}
              onClick={() => { setOtherOpen(false); onSelect(isSel ? '' : opt); }}
              style={{
                padding: '5px 13px', borderRadius: 20, fontSize: 12,
                fontFamily: "'DM Mono',monospace", cursor: 'pointer',
                border: `1px solid ${isSel ? color : `${color}40`}`,
                background: isSel ? color : `${color}0a`,
                color: isSel ? '#070b14' : 'var(--text2)',
                fontWeight: isSel ? 700 : 400, transition: 'all 0.12s',
              }}>
              {opt}
            </button>
          );
        })}
        {/* Other chip */}
        <button
          onClick={toggleOther}
          style={{
            padding: '5px 13px', borderRadius: 20, fontSize: 12,
            fontFamily: "'DM Mono',monospace", cursor: 'pointer',
            border: `1px solid ${(otherOpen || isOtherSelected) ? color : `${color}40`}`,
            background: (otherOpen || isOtherSelected) ? `${color}18` : 'transparent',
            color: (otherOpen || isOtherSelected) ? color : 'var(--text3)',
            fontWeight: 400, transition: 'all 0.12s',
          }}>
          {isOtherSelected ? `✎ ${otherValue}` : 'Other…'}
        </button>
      </div>
      {/* Inline text input when Other is open */}
      {otherOpen && (
        <div style={{ marginTop: 8, display: 'flex', gap: 6 }}>
          <input
            autoFocus
            value={otherText}
            onChange={e => commitOther(e.target.value)}
            onKeyDown={e => { if (e.key === 'Escape') toggleOther(); }}
            placeholder="Type your answer…"
            style={{
              flex: 1, background: 'var(--panel2)', border: `1px solid ${color}55`,
              borderRadius: 5, padding: '6px 10px', fontSize: 12,
              color: 'var(--text)', fontFamily: "'DM Mono',monospace",
              outline: 'none',
            }}
          />
          {otherText.trim() && (
            <button
              onClick={() => setOtherOpen(false)}
              style={{
                padding: '6px 12px', borderRadius: 5, background: color,
                color: '#070b14', border: 'none', fontSize: 11,
                fontFamily: "'DM Mono',monospace", fontWeight: 700, cursor: 'pointer',
              }}>
              ✓
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function QuickReplyPanel({
  text, color, onSend, disabled,
}: { text: string; color: string; onSend: (msg: string) => void; disabled: boolean }) {
  const questions = parseQuestionsFromText(text);
  const [selected, setSelected] = useState<Record<number, string>>({});
  const [open, setOpen] = useState(true);

  // Reset when AI message changes
  const questionKey = questions.map(q => q.index).join(',');
  const prevKey = useRef('');
  useEffect(() => {
    if (prevKey.current !== questionKey) {
      prevKey.current = questionKey;
      setSelected({});
      setOpen(true);
    }
  }, [questionKey]);

  if (questions.length === 0 || !open) return null;

  const allAnswered = questions.every(q => selected[q.index]);
  const selectedCount = questions.filter(q => selected[q.index]).length;

  const buildReply = () => {
    return questions
      .filter(q => selected[q.index])
      .map(q => {
        const val = selected[q.index];
        const display = val.startsWith('__other__:') ? val.slice(10) : val;
        return `${q.index}. ${q.label}: ${display}`;
      })
      .join('\n');
  };

  return (
    /* Sticky popup anchored to bottom of chat scroll area */
    <div style={{
      position: 'sticky', bottom: 12, zIndex: 20,
      marginBottom: 8,
      background: 'var(--panel2)',
      border: `1px solid ${color}44`,
      borderRadius: 12,
      boxShadow: `0 -4px 32px rgba(0,0,0,0.55), 0 0 0 1px ${color}18`,
      overflow: 'hidden',
    }}>
      {/* Header bar */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '10px 14px',
        background: `linear-gradient(90deg, ${color}18, transparent)`,
        borderBottom: `1px solid ${color}22`,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 14 }}>&#9889;</span>
          <span style={{ fontFamily: "'DM Mono',monospace", fontSize: 11, color, letterSpacing: '0.1em' }}>
            QUICK ANSWERS — {selectedCount}/{questions.length} selected
          </span>
        </div>
        <button
          onClick={() => setOpen(false)}
          style={{
            background: 'none', border: 'none', color: 'var(--text4)',
            fontSize: 16, cursor: 'pointer', lineHeight: 1, padding: '2px 6px',
          }}
          title="Dismiss">
          ×
        </button>
      </div>

      {/* Question cards */}
      <div style={{ padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 380, overflowY: 'auto' }}>
        {questions.map(q => (
          <QuestionCard
            key={q.index}
            q={q}
            color={color}
            selected={selected[q.index] ?? ''}
            onSelect={val => setSelected(prev => ({ ...prev, [q.index]: val }))}
          />
        ))}
      </div>

      {/* Footer / send */}
      <div style={{
        padding: '10px 12px',
        borderTop: `1px solid ${color}18`,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10,
      }}>
        <span style={{ fontSize: 11, color: 'var(--text4)', fontFamily: "'DM Mono',monospace" }}>
          {allAnswered ? 'All questions answered' : `${questions.length - selectedCount} remaining`}
        </span>
        <button
          onClick={() => { onSend(buildReply()); setOpen(false); }}
          disabled={disabled || selectedCount === 0}
          style={{
            padding: '8px 20px', borderRadius: 6,
            background: selectedCount > 0 ? color : 'var(--panel3)',
            color: selectedCount > 0 ? '#070b14' : 'var(--text4)',
            border: 'none', fontSize: 12,
            fontFamily: "'DM Mono',monospace", fontWeight: 700,
            cursor: disabled || selectedCount === 0 ? 'default' : 'pointer',
            transition: 'all 0.15s',
          }}>
          Send {selectedCount > 0 ? `${selectedCount} answer${selectedCount > 1 ? 's' : ''}` : 'answers'} →
        </button>
      </div>
    </div>
  );
}

// ---- Welcome card ----
function WelcomeCard({ color, onSuggestion }: { color: string; onSuggestion: (s: string) => void }) {
  const examples = [
    '3-phase BLDC motor controller, 10kW, 48V bus',
    'RF amplifier, 40dBm output, 2.4GHz',
    '48V to 3.3V/5V/12V power supply, 200W total',
  ];
  return (
    <div style={{ background: 'var(--panel2)', border: `1px solid ${color}33`, borderRadius: 10, padding: '20px 22px', marginBottom: 20 }}>
      <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)', marginBottom: 10 }}>
        Welcome to Hardware Pipeline!
      </div>
      <div style={{ fontSize: 13, color: 'var(--text2)', lineHeight: 1.65, marginBottom: 14 }}>
        Tell me what you want to design &mdash; I'll instantly generate a complete{' '}
        <strong style={{ color: 'var(--text)' }}>block diagram, requirements, and BOM</strong>{' '}
        with real component selection. No long questionnaires.
      </div>
      <div style={{ fontSize: 12, color, fontWeight: 600, marginBottom: 8 }}>Examples:</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 14 }}>
        {examples.map((ex, i) => (
          <button key={i} onClick={() => onSuggestion(ex)} style={{ textAlign: 'left', background: `${color}08`, border: `1px solid ${color}22`, borderRadius: 6, padding: '7px 14px', fontSize: 12, color: 'var(--text2)', fontFamily: "'DM Mono',monospace", cursor: 'pointer', transition: 'all 0.15s' }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = color; e.currentTarget.style.color = color; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = `${color}22`; e.currentTarget.style.color = 'var(--text2)'; }}>
            <em>{ex}</em>
          </button>
        ))}
      </div>
      <div style={{ fontSize: 12, color: 'var(--text3)' }}>
        Just describe your design and I'll produce a draft in seconds. &#9889;
      </div>
    </div>
  );
}

/** Strip backend-generated boilerplate that references UI elements that don't exist */
function cleanAiText(text: string): string {
  return text
    .replace(/Click\s+["'\u2018\u2019\u201c\u201d]?Run\s+(?:Full\s+)?Pipeline["'\u2018\u2019\u201c\u201d]?\s+(?:button\s+)?to\s+generate[^\n]*/gi, '')
    .replace(/Click\s+the\s+["'\u2018\u2019\u201c\u201d]?Run\s+(?:Full\s+)?Pipeline["'\u2018\u2019\u201c\u201d]?\s+button[^.]*\./gi, '')
    .replace(/press\s+["'\u2018\u2019\u201c\u201d]?Run\s+(?:Full\s+)?Pipeline["'\u2018\u2019\u201c\u201d][^.]*\./gi, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

// ---- Main ChatView ----
export default function ChatView({ project, phase, phaseStatus, pipelineStarted, messages, onMessages, onStatusChange, onPhaseComplete }: Props) {
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState('');
  const [historyLoaded, setHistoryLoaded] = useState(false);
  // phaseCompleted: true when backend says P1 is completed — hides "Generate Documents" button.
  // Initialized from phaseStatus prop so it's correct even on page reload / project load.
  const [phaseCompleted, setPhaseCompleted] = useState(phaseStatus === 'completed');
  // showApproveCard: shows the approve / pipeline-running card
  const [showApproveCard, setShowApproveCard] = useState(phaseStatus === 'completed');
  // approveClicked: true once P2+ pipeline has actually been kicked off.
  // Driven by pipelineStarted prop (P2+ has in_progress or completed activity),
  // NOT just by phaseStatus — P1 can be done without the pipeline having started.
  const [approveClicked, setApproveClicked] = useState(pipelineStarted);

  // Keep state in sync when props change (e.g. status poll)
  useEffect(() => {
    if (phaseStatus === 'completed') {
      setPhaseCompleted(true);
      setShowApproveCard(true);
    }
  }, [phaseStatus]);

  useEffect(() => {
    if (pipelineStarted) setApproveClicked(true);
  }, [pipelineStarted]);
  const bottomRef = useRef<HTMLDivElement>(null);
  const color = phase.color;

  // Load conversation history from backend on first mount
  const loadHistory = useCallback(async () => {
    if (!project || historyLoaded || messages.length > 0) { setHistoryLoaded(true); return; }
    try {
      const history = await api.getConversationHistory(project.id);
      if (history.length > 0) {
        onMessages(history.map(m => ({
          role: m.role === 'assistant' ? 'ai' : 'user' as 'user' | 'ai',
          text: m.content,
        })));
      }
    } catch { /* silent */ }
    setHistoryLoaded(true);
  }, [project, historyLoaded, messages.length]);

  useEffect(() => { loadHistory(); }, [loadHistory]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  // streaming intentionally excluded — scrolling every 16ms causes jank
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages, showApproveCard, phaseCompleted]);

  /** Silently finalize Phase 1 — no user bubble, no input echo */
  const finalizePhase = async () => {
    if (!project || loading) return;
    setLoading(true);
    setStreaming('');
    try {
      const result = await api.chat(project.id, '__FINALIZE__');
      const rawText = result.text || 'Requirements finalized. Reviewing documents…';
      const cleanText = cleanAiText(rawText);
      let idx = 0;
      const interval = setInterval(() => {
        idx = Math.min(idx + 16, cleanText.length);
        setStreaming(cleanText.slice(0, idx));
        if (idx >= cleanText.length) {
          clearInterval(interval);
          onMessages([...messages, { role: 'ai', text: cleanText }]);
          setStreaming('');
          setLoading(false);
          onStatusChange();
          setPhaseCompleted(true);
          setShowApproveCard(true);
        }
      }, 16);
    } catch {
      onMessages([...messages, { role: 'ai', text: 'Error connecting to backend. Make sure FastAPI is running on port 8000.' }]);
      setStreaming('');
      setLoading(false);
    }
  };

  const sendMessage = async (text: string) => {
    if (!project || !text.trim() || loading) return;
    const updated = [...messages, { role: 'user' as const, text }];
    onMessages(updated);
    setInput('');
    setLoading(true);
    setStreaming('');
    // Hide the approve card while the user is actively chatting — it will
    // re-appear after the next AI response if phaseComplete is still true.
    if (showApproveCard && !approveClicked) setShowApproveCard(false);

    try {
      const result = await api.chat(project.id, text);
      // Strip backend boilerplate referencing non-existent UI buttons
      // If the backend returned an empty response, show a helpful fallback
      const rawText = result.text || 'I processed your request. Check the Documents tab to see updated outputs, or try rephrasing your request.';
      const cleanText = cleanAiText(rawText);
      // Typewriter animation — 16ms/16chars (~60fps, ~1000 chars/sec)
      // Streaming div uses plain pre-wrap text (no markdown parsing per tick) for smooth rendering.
      // Full markdown is only rendered once, when the message is committed to messages[].
      let idx = 0;
      const interval = setInterval(() => {
        idx = Math.min(idx + 16, cleanText.length);
        setStreaming(cleanText.slice(0, idx));
        if (idx >= cleanText.length) {
          clearInterval(interval);
          onMessages([...updated, { role: 'ai', text: cleanText }]);
          setStreaming('');
          setLoading(false);
          onStatusChange();
          if (result.phaseComplete) {
            setPhaseCompleted(true);
            setShowApproveCard(true);
          }
        }
      }, 16);
    } catch {
      onMessages([...updated, { role: 'ai', text: 'Error connecting to backend. Make sure FastAPI is running on port 8000.' }]);
      setStreaming('');
      setLoading(false);
    }
  };

  return (
    <div style={{ paddingTop: 20, display: 'flex', flexDirection: 'column', minHeight: '100%' }}>
      {messages.length === 0 && !loading && historyLoaded && (
        <WelcomeCard color={color} onSuggestion={sendMessage} />
      )}

      {messages.map((msg, i) => (
        <ChatMessageItem key={i} msg={msg} color={color} />
      ))}

      {/* Quick-reply option chips — shown after last AI message when not loading/complete */}
      {!loading && !approveClicked && messages.length > 0 && messages[messages.length - 1]?.role === 'ai' && (
        <QuickReplyPanel
          text={messages[messages.length - 1].text}
          color={color}
          onSend={sendMessage}
          disabled={loading}
        />
      )}

      {loading && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ padding: '14px 18px', borderRadius: 8, background: 'var(--panel2)', border: `1px solid ${color}33` }}>
            <div style={{ fontSize: 10, color, marginBottom: 8, letterSpacing: '0.1em' }}>AI RESPONSE</div>
            {streaming
              /* Raw pre-wrap during typewriter — no markdown parsing per tick */
              ? <div style={{ whiteSpace: 'pre-wrap', fontSize: 13, color: 'var(--text2)', lineHeight: 1.65 }}>{streaming}</div>
              : <span style={{ color: 'var(--text4)', fontSize: 13 }}>Thinking<span style={{ animation: 'blink 1s step-end infinite' }}>...</span></span>
            }
          </div>
        </div>
      )}

      {/* Approve card — shown when requirements are ready */}
      {showApproveCard && (
        <div className="fade-up" style={{
          marginBottom: 16, borderRadius: 10,
          border: `1px solid ${color}${approveClicked ? '40' : '70'}`,
          overflow: 'hidden',
        }}>
          {approveClicked ? (
            /* ── Pipeline is running ── */
            <div style={{
              padding: '13px 18px', display: 'flex', alignItems: 'center', gap: 12,
              background: `linear-gradient(135deg, ${color}08, transparent)`,
            }}>
              <div style={{
                width: 26, height: 26, borderRadius: '50%', background: `${color}20`,
                border: `2px solid ${color}`, display: 'flex', alignItems: 'center',
                justifyContent: 'center', fontSize: 13, color, flexShrink: 0,
              }}>&#10003;</div>
              <div>
                <div style={{ fontFamily: "'Syne',sans-serif", fontSize: 13, fontWeight: 800, color, marginBottom: 2 }}>
                  Phase 1 complete &#8212; pipeline running P2 &#8594; P8
                </div>
                <div style={{ fontSize: 11.5, color: 'var(--text3)' }}>
                  Documents generated. You can keep chatting while the pipeline runs.
                </div>
              </div>
            </div>
          ) : (
            /* ── Waiting for review & approval ── */
            <div style={{ padding: '16px 18px', display: 'flex', alignItems: 'center', gap: 14 }}>
              <div style={{
                width: 24, height: 24, borderRadius: '50%', background: `${color}20`,
                border: `1.5px solid ${color}`, display: 'flex', alignItems: 'center',
                justifyContent: 'center', fontSize: 12, color, flexShrink: 0,
              }}>&#9711;</div>
              <div style={{ flex: 1 }}>
                <div style={{ fontFamily: "'Syne',sans-serif", fontSize: 13, fontWeight: 800, color, marginBottom: 3 }}>
                  Requirements ready &#8212; review above, then approve
                </div>
                <div style={{ fontSize: 11.5, color: 'var(--text3)', lineHeight: 1.5 }}>
                  Use the chat below to request changes, then approve to run the full pipeline.
                </div>
              </div>
              <button
                onClick={() => { setApproveClicked(true); onPhaseComplete(); }}
                style={{
                  padding: '9px 20px', borderRadius: 6, border: 'none', background: color,
                  color: '#070b14', fontSize: 12, fontFamily: "'Syne',sans-serif",
                  fontWeight: 800, cursor: 'pointer', letterSpacing: '0.03em',
                  transition: 'all 0.15s', flexShrink: 0,
                }}
                onMouseEnter={e => { e.currentTarget.style.opacity = '0.85'; e.currentTarget.style.transform = 'translateY(-1px)'; }}
                onMouseLeave={e => { e.currentTarget.style.opacity = '1'; e.currentTarget.style.transform = 'none'; }}
              >
                &#10003; Approve &amp; Run
              </button>
            </div>
          )}
        </div>
      )}

      {/* Generate Documents button — shown after AI replies, hidden once phase is complete */}
      {!phaseCompleted && !loading && messages.some(m => m.role === 'ai') && (
        <div style={{ marginTop: 12, marginBottom: 4 }}>
          <button
            onClick={() => finalizePhase()}
            disabled={loading}
            style={{
              width: '100%', padding: '11px 20px', borderRadius: 6,
              border: `1px solid ${color}66`,
              background: `${color}18`, color: color, fontSize: 12.5,
              fontFamily: "'DM Mono',monospace", fontWeight: 600, cursor: 'pointer',
              letterSpacing: '0.04em', transition: 'all 0.15s',
            }}
            onMouseEnter={e => { e.currentTarget.style.background = `${color}30`; e.currentTarget.style.borderColor = color; }}
            onMouseLeave={e => { e.currentTarget.style.background = `${color}18`; e.currentTarget.style.borderColor = `${color}66`; }}
          >
            &#9889; Generate Documents &amp; Complete Phase 1 &rarr;
          </button>
        </div>
      )}

      <div ref={bottomRef} />

      {/* Input — sticky at the bottom of the viewport within the scrolling center panel */}
      <div style={{
        position: 'sticky', bottom: 0, zIndex: 10,
        background: 'linear-gradient(to bottom, transparent 0%, var(--navy) 18px)',
        paddingTop: 16, paddingBottom: 12, marginTop: 'auto',
      }}>
      <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end' }}>
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(input); } }}
          placeholder={showApproveCard && !approveClicked ? 'Request changes to the requirements, or approve above...' : showApproveCard ? 'Keep chatting while pipeline runs...' : 'Describe your hardware design...'}
          disabled={loading}
          rows={3}
          style={{ flex: 1, background: 'var(--panel)', border: `1px solid ${showApproveCard ? color + '44' : 'var(--panel3)'}`, borderRadius: 6, padding: '10px 13px', fontSize: 13, color: 'var(--text)', fontFamily: "'DM Mono',monospace", resize: 'none', transition: 'border-color 0.2s' }}
        />
        <button onClick={() => sendMessage(input)} disabled={!input.trim() || loading || !project}
          style={{ padding: '10px 20px', borderRadius: 6, border: 'none', background: input.trim() && !loading ? color : 'var(--panel2)', color: input.trim() && !loading ? 'var(--navy)' : 'var(--text4)', fontSize: 12, fontFamily: "'DM Mono',monospace", fontWeight: 500, cursor: input.trim() && !loading ? 'pointer' : 'default', transition: 'all 0.15s', alignSelf: 'stretch' }}>
          Send
        </button>
      </div>
      </div>
    </div>
  );
}
