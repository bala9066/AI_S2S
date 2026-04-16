import { useState, useRef, useEffect, useCallback, memo } from 'react';
import type { Project, PhaseMeta } from '../types';
import { api } from '../api';
import { ensureMermaid, purgeMermaidScratch, nextMermaidId } from '../utils/mermaid';
import { parseQuestionsFromAI, shouldShowQuestions, type QuestionCard as QuestionCardType } from '../data/questionSchema';

export interface ChatMessage { role: 'user' | 'ai'; text: string; }

/** Truncate long questions to fit in cards */
function truncateQuestion(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength - 3) + '...';
}

/** Sanitise AI-generated Mermaid code — shared logic kept in sync with DocumentsView */
function sanitizeMermaid(raw: string): string {
  let code = raw.trim().replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  // Strip %%{ init }%% frontmatter and %% comments
  code = code.replace(/^%%\{[\s\S]*?\}%%\s*/m, '');
  code = code.replace(/%%[^\n]*/g, '');
  // Arrow normalisations
  code = code.replace(/\u2014\u2014>/g, '-->').replace(/\u2014>/g, '-->');
  code = code.replace(/——>/g, '-->').replace(/—>/g, '-->');
  code = code.replace(/==>/g, '-->');
  code = code.replace(/(\w)\s*->\s*(\w)/g, '$1 --> $2');
  // Normalise graph → flowchart
  code = code.replace(/^graph\s+(TD|LR|TB|RL|BT)/im, 'flowchart $1');
  code = code.replace(/^(flowchart)\n(TD|LR|TB|RL|BT)\b/m, '$1 $2');
  // Join lines where [ is opened but not closed (multi-line node labels)
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
  // Literal \n → space; strip all HTML tags; decode HTML entities
  code = code.replace(/\\n/g, ' ');
  code = code.replace(/&lt;/g, '(').replace(/&gt;/g, ')').replace(/&amp;/g, 'and').replace(/&nbsp;/g, ' ');
  code = code.replace(/<[^>]+>/gi, ' ');
  // Fix "NODE [label]" → "NODE[label]"
  code = code.split('\n').map(line => {
    if (/^\s*subgraph\b/.test(line)) return line.replace(/^(\s*subgraph\s+[\w-]+)\s+\[/, '$1[');
    return line.replace(/(\w)\s+\[/g, '$1[');
  }).join('\n');
  // Sanitize node labels — strip arrows FIRST
  // Angle brackets → spaces (NOT parentheses — they cause parse errors)
  // Parentheses → spaces (node labels like "Component (PartNumber)" break Mermaid)
  // IMPORTANT: Remove ALL dash sequences (2 or more) — they get mistaken for edge arrows
  const sanitizeLabel = (inner: string) =>
    inner
      .replace(/-->/g, ' ').replace(/->/g, ' ')  // strip arrows before anything else
      .replace(/</g, ' ').replace(/>/g, ' ')  // angle brackets to spaces, NOT parens
      .replace(/\(/g, ' ').replace(/\)/g, ' ')  // parens break Mermaid's node parser
      .replace(/_/g, '-')  // underscores trigger subscript parsing
      .replace(/&(?!amp;|lt;|gt;|#)/g, 'and')
      .replace(/"/g, ' ').replace(/'/g, ' ')  // quotes confuse the parser
      .replace(/#/g, ' ')
      .replace(/\|/g, '/')
      .replace(/@/g, ' ')  // @ can cause issues in some Mermaid versions
      .replace(/-{2,}/g, ' ')  // Remove ALL dash sequences — they become arrows!
      .replace(/^[-—=]+|[—=-]+$/g, ' ')  // Remove standalone dashes at start/end
      .replace(/\s{2,}/g, ' ')  // Clean up multiple spaces
      .trim();
  code = code.replace(/\[([^\]]*)\]/g, (_m, inner: string) => `[${sanitizeLabel(inner)}]`);
  code = code.replace(/\(([^)]*)\)/g, (_m, inner: string) => `(${sanitizeLabel(inner)})`);
  code = code.replace(/\{([^}]*)\}/g, (_m, inner: string) => `{${sanitizeLabel(inner)}}`);
  code = code.replace(/"([^"]+)"/g, (_m, inner: string) => `"${sanitizeLabel(inner)}"`);
  // Edge labels: --> |label| node
  code = code.replace(/\|([^|]+)\|/g, (_m, inner: string) => `|${sanitizeLabel(inner)}|`);
  // State diagram colon-label sanitization — use spaces NOT parentheses
  if (first.startsWith('statediagram')) {
    code = code.split('\n').map(line => {
      const m = line.match(/^(\s*.*?-->\s*\S+\s*:)(.*)$/);
      if (m) {
        const label = m[2].replace(/>/g, ' ').replace(/</g, ' ').replace(/:/g, ',');
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
    /\?\s+(?=(?:Do|Does|Did|Is|Are|Was|Were|Will|Would|Can|Could|Should|Have|Has|What|Which|How|Where|When|Who|Any|Please|Specify|Indicate|Select|If|For|In|With|Provide|List|Describe|Define|Confirm|Tell)\b)/
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
  // Debug: log a sample of the text for troubleshooting
  if (typeof window !== 'undefined' && (window as any).__debugQuickReply) {
    console.log('[QuickReply] Parsing text:', text.substring(0, 200));
  }

  // Helper: strip leading em-dash / dash that AIs emit after the label separator
  // e.g. "**Label** — body" → body captured as "— body" → we strip to "body"
  const stripLeadingDash = (s: string) => s.replace(/^[—–\-]\s+/, '').trim();

  // ── Format A: "1. **Label**: body?" — label + body on same line ──────────
  {
    const questions: ParsedQuestion[] = [];
    // More permissive regex: allows label to contain more chars, body can be shorter
    const lineRe = /^(\d+)\.\s+\*{0,2}([^:*\n]{1,60})\*{0,2}[:\s]+(.{3,500})$/gm;
    let m: RegExpExecArray | null;
    while ((m = lineRe.exec(text)) !== null) {
      const idx = parseInt(m[1]);
      const label = m[2].trim();
      const body = stripLeadingDash(m[3]);
      questions.push({ index: idx, label, body, options: extractOptions(body) });
    }
    if (questions.length > 0) {
      if (typeof window !== 'undefined' && (window as any).__debugQuickReply) {
        console.log('[QuickReply] Format A matched:', questions);
      }
      return expandAndRenumber(questions);
    }
  }

  // ── Format B: numbered section headers + bullet points underneath ─────────
  // e.g.:  "1. **Application**\n• What is this driving?\n• Temp range?"
  // FIX D: When a bullet ends with ":" it's an intro for sub-options.
  // Collect following non-"?" bullets as chip options for that intro question.
  {
    const questions: ParsedQuestion[] = [];
    const lines = text.split('\n');
    let sectionLabel = '';
    let qIdx = 0;
    let i = 0;

    while (i < lines.length) {
      const line = lines[i];

      // Section header: "1. **Label**" or "1. Label" (no colon body after)
      const secM = line.match(/^\d+\.\s+\*{0,2}([^*\n:]{2,60})\*{0,2}\s*$/);
      if (secM) { sectionLabel = secM[1].trim(); i++; continue; }

      // Bullet line under a section
      if (sectionLabel) {
        const bulletM = line.match(/^\s*[•\-\*]\s+(.+)$/);
        if (bulletM) {
          const body = stripLeadingDash(bulletM[1]);

          // FIX D: If this bullet ends with ":" or "Do you need:" — collect
          // following non-"?" bullets as sub-options for this question
          if (/:\s*$/.test(body) || /\b(need|want|choose|select|prefer)\s*:\s*$/i.test(body)) {
            const subOptions: string[] = [];
            let j = i + 1;
            while (j < lines.length) {
              const subM = lines[j].match(/^\s*[•\-\*]\s+(.+)$/);
              if (!subM) break;
              const subBody = stripLeadingDash(subM[1]).replace(/[?!,]+$/, '').trim();
              // Sub-bullet that's a question itself (ends with ?) → stop merging
              if (/\?\s*$/.test(subM[1])) break;
              if (subBody.length > 2 && subBody.length < 60) {
                // Strip trailing ", or" and clean up
                const cleaned = subBody.replace(/,?\s*or\s*$/i, '').trim();
                if (cleaned.length > 2) subOptions.push(cleaned);
              }
              j++;
            }
            if (subOptions.length >= 2) {
              qIdx++;
              questions.push({
                index: qIdx, label: sectionLabel,
                body: body.replace(/:\s*$/, '?'),
                options: subOptions.slice(0, 5).map(s => {
                  const t = s.charAt(0).toUpperCase() + s.slice(1);
                  return t.split(/\s+/).length <= 5 ? t : t.split(/\s+/).slice(0, 5).join(' ');
                }),
              });
              i = j; // skip past the sub-bullets we consumed
              continue;
            }
          }

          // Regular bullet — standalone question
          // Skip horizontal rules and non-question content
          if (/^-{2,}$/.test(body.trim()) || body.trim().length < 6) { i++; continue; }
          qIdx++;
          questions.push({ index: qIdx, label: sectionLabel, body, options: extractOptions(body) });
          i++;
          continue;
        }
      }
      i++;
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
    // More permissive: reduce minimum body length from 10 to 5 chars
    const plainRe = /^(\d+)\.\s+(.{5,500}[?!])\s*$/gm;
    let dm: RegExpExecArray | null;
    while ((dm = plainRe.exec(text)) !== null) {
      const idx = parseInt(dm[1]);
      const body = stripLeadingDash(dm[2]);
      // Derive a short label from the first 4 words of the question
      const words = body.replace(/[?!.]/g, '').split(/\s+/);
      const label = words.slice(0, 4).join(' ');
      questions.push({ index: idx, label, body, options: extractOptions(body) });
    }
    if (questions.length > 0) {
      if (typeof window !== 'undefined' && (window as any).__debugQuickReply) {
        console.log('[QuickReply] Format D matched:', questions);
      }
      return expandAndRenumber(questions);
    }
  }

  // ── Format E: prose questions — bold headings + "Also/For" sentences ───────
  // Catches AI responses that don't use numbered lists, e.g.:
  //   "**Current sensing** — Do you want:\n• opt1\n• opt2?"
  //   "Also, for position — Hall sensors, encoder, or sensorless?"
  {
    const questions: ParsedQuestion[] = [];
    const lines = text.split('\n');
    let i = 0;

    while (i < lines.length) {
      const line = lines[i].trim();

      // Bold standalone heading: "**Topic** — optional body text"
      const boldM = line.match(/^\*{2}([^*\n]{3,60})\*{2}[—\-:\s]*(.*)$/);
      if (boldM) {
        const sectionLabel = boldM[1].replace(/:$/, '').trim();
        // Collect body: rest of heading line + following lines until blank/next heading
        const bodyLines: string[] = [];
        if (boldM[2].trim()) bodyLines.push(boldM[2].trim());
        i++;
        while (i < lines.length && lines[i].trim() && !/^\*{2}/.test(lines[i])) {
          bodyLines.push(lines[i].trim());
          i++;
        }
        const body = bodyLines.join('\n');
        if (body.length > 5 && (body.includes('?') || body.includes('•') || /\bor\b/i.test(body))) {
          questions.push({ index: questions.length + 1, label: sectionLabel, body, options: extractOptions(body) });
        }
        continue;
      }

      // Inline prose question: sentence ending in "?" with "or" / question words
      if (line.endsWith('?') && line.length > 15 &&
          /\b(or|do you|what|which|how|any|is there|will|can you|hall|encoder|sensorless)\b/i.test(line)) {
        const words = line.replace(/[?.,]/g, '').split(/\s+/);
        const label = words.slice(0, 4).join(' ');
        questions.push({ index: questions.length + 1, label, body: line, options: extractOptions(line) });
      }

      i++;
    }

    if (questions.length > 0) return expandAndRenumber(questions);
  }

  // ── Format F: ULTRA-PERMISSIVE CATCH-ALL ───────────────────────────────────
  // Last resort: find ANY numbered pattern "1." followed by some text
  // This catches edge cases where AI uses unusual formatting
  {
    const questions: ParsedQuestion[] = [];
    const lines = text.split('\n');
    let qIdx = 0;

    for (const line of lines) {
      // Match "1." or "1)" followed by any text (very permissive)
      const numMatch = line.match(/^\s*(\d+)[\.)]\s+(.{5,500})\s*$/);
      if (numMatch) {
        qIdx++;
        const body = stripLeadingDash(numMatch[2]);
        // Extract label from first few words
        const words = body.replace(/[?.,]/g, '').split(/\s+/);
        const label = words.slice(0, 3).join(' ');
        questions.push({ index: qIdx, label, body, options: extractOptions(body) });
      }
    }

    if (questions.length >= 2) {
      if (typeof window !== 'undefined' && (window as any).__debugQuickReply) {
        console.log('[QuickReply] Format F (catch-all) matched:', questions);
      }
      return expandAndRenumber(questions);
    }
  }

  if (typeof window !== 'undefined' && (window as any).__debugQuickReply) {
    console.log('[QuickReply] No format matched, returning empty array');
  }
  return [];
}

function extractOptions(body: string): string[] {
  // ── Normalise chip text ────────────────────────────────────────────────────
  const cleanBody = body.replace(/^[—–\-]\s+/, '').trim();

  const normalizeChip = (s: string): string => {
    let t = s.trim()
      .replace(/^(or|and)\s+/i, '')
      .replace(/^(a|an|the|just|only)\s+/i, '')
      .replace(/[?!.]+$/, '')
      .trim();
    return t.length > 0 ? t.charAt(0).toUpperCase() + t.slice(1) : t;
  };

  // Per-part word-count guard — filter individually, never reject entire group
  const chipWords = (s: string) => normalizeChip(s).split(/\s+/).length;
  const isShortChip = (s: string) => chipWords(s) <= 4;

  // ── Bullet list options — "• opt1\n• opt2\n• opt3?" ──────────────────────
  const bulletMatches = Array.from(cleanBody.matchAll(/[•\-\*]\s+\*{0,2}([^\n•\-\*]{3,60})\*{0,2}/g));
  if (bulletMatches.length >= 2) {
    const parts = bulletMatches
      .map(m => normalizeChip(m[1].replace(/\s*\([^)]*\).*$/, '').trim()))
      .filter(s => s.length > 1 && s.length < 40 && isShortChip(s));
    if (parts.length >= 2) return parts.slice(0, 5);
  }

  // ── Domain shortcuts (high-confidence) ─────────────────────────────────────

  const tempKeyword = /\b(temperature|thermal|operating\s+temp|temp\s+range|grade)\b/i.test(cleanBody);
  const tempGrades  = /\b(commercial|industrial|automotive|mil.?spec|military)\b/i.test(cleanBody) &&
                      /(-\d+|°[CF]|ambient|outdoor)/i.test(cleanBody);
  if (tempKeyword || tempGrades) {
    const chips: string[] = [];
    if (/commercial/i.test(cleanBody))         chips.push('Commercial (0-70C)');
    if (/industrial/i.test(cleanBody))         chips.push('Industrial (-40-85C)');
    if (/automotive/i.test(cleanBody))         chips.push('Automotive (-40-105C)');
    if (/mil.?spec|military/i.test(cleanBody)) chips.push('MIL-SPEC (-55-125C)');
    if (chips.length >= 2) return chips;
    return ['Commercial (0-70C)', 'Industrial (-40-85C)', 'Automotive (-40-105C)', 'MIL-SPEC (-55-125C)'];
  }

  if (/\b(forced\s+air|natural\s+convect|conduction.cool|heatsink|heat\s*sink)\b/i.test(cleanBody)) {
    return ['Forced air (fan)', 'Natural convection', 'Conduction-cooled'];
  }

  // ══════════════════════════════════════════════════════════════════════════
  // FIX A: Try main body "A, B, or C" list BEFORE e.g. parens
  // This ensures "CW tone, pulsed, or digitally modulated (e.g., QPSK, QAM)"
  // extracts [CW tone, Pulsed, Digitally modulated] — not [QPSK, QAM]
  // ══════════════════════════════════════════════════════════════════════════
  const bodyClean = cleanBody.replace(/\s*\([^)]*\)/g, '').replace(/\s+/g, ' ').trim();
  const lastClause = bodyClean.split(/[:\u2014\u2013]/).pop()?.trim() ?? bodyClean;

  const tryExtractOrList = (candidate: string): string[] | null => {
    const endOrRe = /\b(\w[\w\s/\-]{0,28})(?:,\s*\w[\w\s/\-]{0,28})*(?:,?\s*or\s+\w[\w\s/\-]{0,28})\s*[?!.]?\s*$/i;
    const m = candidate.match(endOrRe);
    if (!m) return null;
    const raw = m[0].replace(/[?!.]\s*$/, '').trim();
    const parts = raw
      .split(/,\s*(?:or\s+)?|\s+or\s+/)
      .map(s => normalizeChip(s))
      .filter(s => s.length > 1 && s.length < 40 && isShortChip(s));
    return parts.length >= 2 ? parts.slice(0, 5) : null;
  };

  const endResult = tryExtractOrList(lastClause);
  if (endResult) return endResult;

  const firstSentence = lastClause.split('?')[0];
  if (firstSentence && firstSentence !== lastClause) {
    const sentenceResult = tryExtractOrList(firstSentence + '?');
    if (sentenceResult) return sentenceResult;
  }

  // ── e.g./i.e. parentheticals — fallback when main body has no list ────────
  const egParens = Array.from(cleanBody.matchAll(/\(\s*(?:e\.g\.|i\.e\.)[.,]?\s*([^)]{4,120})\)/gi));
  for (const pm of egParens) {
    const inner = pm[1].replace(/^(?:e\.g\.|i\.e\.)[.,]?\s*/i, '');
    const parts = inner
      .split(/[,/]|\s+or\s+/)
      .map(s => normalizeChip(s))
      .filter(s => s.length > 1 && s.length < 32 && isShortChip(s));
    if (parts.length >= 2) return parts.slice(0, 5);
  }

  // ── Plain paren with 3+ comma-separated short options ────────────────────
  const plainParens = Array.from(cleanBody.matchAll(/\(([^)]{6,120})\)/gi));
  for (const pm of plainParens) {
    const inner = pm[1].trim();
    if (/\be\.g\b|\bi\.e\b/i.test(inner)) continue;
    const parts = inner
      .split(/[,/]|\s+or\s+/)
      .map(s => normalizeChip(s))
      .filter(s => s.length > 1 && s.length < 32 && isShortChip(s));
    if (parts.length >= 2) return parts.slice(0, 5);
  }

  // ══════════════════════════════════════════════════════════════════════════
  // FIX C: Binary "X or Y" mid-sentence — catches "isolated or non-isolated",
  // "on-board PLL or external reference", "FCC/CE compliance or controlled env"
  // ══════════════════════════════════════════════════════════════════════════
  {
    // Pattern: "need/want/use/prefer X or Y" where X,Y are 1-4 words
    const binaryM = bodyClean.match(/\b(?:need|want|use|prefer|require|provide|have)?\s*(\w[\w\s/\-]{0,30}?)\s+or\s+(?:is\s+(?:this|it)\s+(?:a\s+|an\s+|for\s+(?:a\s+)?)?)?(\w[\w\s/\-]{0,30}?)(?:\s+(?:for|to|in|on|at|from|with|that|which|buck|boost|converter|design|board|module|environment|reference|provided)\b|\?|$)/i);
    if (binaryM) {
      const a = normalizeChip(binaryM[1]);
      const b = normalizeChip(binaryM[2]);
      if (a.length > 1 && b.length > 1 && isShortChip(a) && isShortChip(b) && a !== b) {
        return [a, b];
      }
    }
    // Simpler fallback: "X or Y?" at or near end of sentence
    const simpleOr = bodyClean.match(/\b(\w[\w\s/\-]{0,20}?)\s+or\s+(\w[\w\s/\-]{0,20}?)\s*\?/i);
    if (simpleOr) {
      const a = normalizeChip(simpleOr[1]);
      const b = normalizeChip(simpleOr[2]);
      if (a.length > 1 && b.length > 1 && isShortChip(a) && isShortChip(b) && a !== b) {
        return [a, b];
      }
    }
  }

  // ── "whether X or Y" ───────────────────────────────────────────────────────
  const whetherM = cleanBody.match(/whether\s+(?:you\s+(?:can|need|should|want|prefer)\s+)?(.{3,35}?)\s+or\s+(?:need\s+|use\s+)?(.{3,35}?)(?:\?|$|\s*\()/i);
  if (whetherM) {
    const a = normalizeChip(whetherM[1]);
    const b = normalizeChip(whetherM[2]);
    if (isShortChip(a) && isShortChip(b) && a.length > 2 && b.length > 2) return [a, b];
  }

  // ══════════════════════════════════════════════════════════════════════════
  // FIX B: Yes/No — but NEVER for What/Which/How/Where/When questions
  // ══════════════════════════════════════════════════════════════════════════
  const isWh = /^\s*(what|which|how|where|when|describe|list|specify|name)\b/i.test(cleanBody);
  if (!isWh && /\?/.test(cleanBody) && !/\bor\b/i.test(cleanBody) &&
      /\b(do you|is there|are there|will|should|does|can you|have you|is it|would you)\b/i.test(cleanBody)) {
    return ['Yes', 'No'];
  }

  // ══════════════════════════════════════════════════════════════════════════
  // FIX E: Domain shortcuts for common hardware quantities (last resort)
  // Guarantees every question gets chips — never return empty.
  // ══════════════════════════════════════════════════════════════════════════
  if (/\b(bandwidth|modulation\s+bw|channel\s+bw)\b/i.test(cleanBody)) {
    return ['Narrowband <1 MHz', '1-50 MHz', 'Wideband 50-500 MHz', '>500 MHz'];
  }
  if (/\b(data\s+rate|bit\s*rate|throughput|baud)\b/i.test(cleanBody)) {
    return ['<1 Mbps', '1-100 Mbps', '100 Mbps - 1 Gbps', '>1 Gbps'];
  }
  if (/\b(frequency|freq)\b/i.test(cleanBody) && /\b(operating|center|carrier|lo)\b/i.test(cleanBody)) {
    return ['<1 GHz', '1-6 GHz', '6-18 GHz', '>18 GHz'];
  }
  if (/\b(input\s+voltage|supply\s+voltage|bus\s+voltage|main\s+voltage)\b/i.test(cleanBody)) {
    return ['5V', '12V', '24V', '48V', 'AC mains'];
  }
  if (/\b(max\s+current|output\s+current|load\s+current)\b/i.test(cleanBody)) {
    return ['<1A', '1-10A', '10-50A', '>50A'];
  }
  if (/\b(output\s+power|transmit\s+power|pa\s+power)\b/i.test(cleanBody)) {
    return ['<1W', '1-10W', '10-50W', '>50W'];
  }
  if (/\b(efficiency|pae|drain\s+efficiency)\b/i.test(cleanBody)) {
    return ['<20%', '20-40%', '40-60%', '>60%'];
  }
  if (/\b(interface|protocol|bus)\b/i.test(cleanBody) && /\b(data|baseband|digital|fpga)\b/i.test(cleanBody)) {
    return ['SPI', 'I2C', 'UART', 'JESD204B', 'Parallel'];
  }
  if (/\b(compliance|certification|regulatory|fcc|ce\b)/i.test(cleanBody)) {
    return ['FCC/CE required', 'MIL-STD', 'Lab/R&D only'];
  }
  if (/\b(form.?factor|enclosure|size|rack|handheld)\b/i.test(cleanBody)) {
    return ['1U rack-mount', 'Desktop', 'Handheld', 'PCB-only'];
  }
  if (/\b(gain|amplif)/i.test(cleanBody)) {
    return ['Low (<10 dB)', 'Medium (10-30 dB)', 'High (>30 dB)'];
  }
  if (/\b(isolated|non.?isolated)\b/i.test(cleanBody)) {
    return ['Isolated', 'Non-isolated'];
  }
  if (/\b(clock|reference|oscillator|pll|synthesizer)\b/i.test(cleanBody)) {
    return ['On-board PLL', 'External reference', 'Crystal oscillator'];
  }

  // Ultimate fallback: if question ends with "?", return Yes/No
  if (/\?\s*$/.test(cleanBody)) return ['Yes', 'No'];

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
        {/* Custom answer — small pencil icon, not "Other..." text */}
        <button
          onClick={toggleOther}
          title="Type a custom answer"
          style={{
            padding: '5px 10px', borderRadius: 20, fontSize: 12,
            fontFamily: "'DM Mono',monospace", cursor: 'pointer',
            border: `1px solid ${(otherOpen || isOtherSelected) ? color : `${color}25`}`,
            background: (otherOpen || isOtherSelected) ? `${color}18` : 'transparent',
            color: (otherOpen || isOtherSelected) ? color : 'var(--text4)',
            fontWeight: 400, transition: 'all 0.12s',
          }}>
          {isOtherSelected ? otherValue : '+'}
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

// ── SchemaQuestionCard ──────────────────────────────────────────────────────
// Question card using pre-defined schema (QuestionCardType from questionSchema)
function SchemaQuestionCard({
  question, color, selected, onSelect,
}: {
  question: QuestionCardType;
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
        {question.label.toUpperCase()}
      </div>
      <div style={{ fontSize: 12.5, color: 'var(--text)', marginBottom: 10, lineHeight: 1.5 }}>
        {truncateQuestion(question.question, 80)}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        {question.options.map(opt => {
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
        {/* Other... button if allowOther is true */}
        {question.allowOther !== false && (
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
        )}
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
  aiMessage, designDescription, color, onSend, disabled,
}: {
  aiMessage: string;
  designDescription: string;
  color: string;
  onSend: (msg: string) => void;
  disabled: boolean;
}) {
  // Parse AI's questions to extract labels and options dynamically
  const questions = parseQuestionsFromAI(aiMessage);
  const [selected, setSelected] = useState<Record<string, string>>({});
  const [dismissed, setDismissed] = useState(false);

  // Check if we should show questions at all
  if (questions.length === 0 || dismissed || !shouldShowQuestions(aiMessage, designDescription)) {
    return null;
  }

  // Reset when AI message changes (simple heuristic: check first 100 chars)
  const questionKey = questions.map(q => q.id).join(',') + aiMessage.slice(0, 100);
  const prevKey = useRef('');
  useEffect(() => {
    if (prevKey.current !== questionKey) {
      prevKey.current = questionKey;
      setSelected({});
      setDismissed(false);
    }
  }, [questionKey]);

  const allAnswered = questions.every(q => selected[q.id]);
  const selectedCount = questions.filter(q => selected[q.id]).length;

  // ── Optional "Any Specific Requirements?" free-text card ─────────────────
  const [specificReqs, setSpecificReqs] = useState('');

  // Reset when question set changes
  useEffect(() => {
    setSpecificReqs('');
  }, [questionKey]);

  const buildReply = () => {
    const lines = questions
      .filter(q => selected[q.id])
      .map(q => {
        const val = selected[q.id];
        const display = val.startsWith('__other__:') ? val.slice(10) : val;
        return `${q.label}: ${display}`;
      });
    if (specificReqs.trim()) {
      lines.push(`Additional requirements: ${specificReqs.trim()}`);
    }
    return lines.join('\n');
  };

  const canSend = selectedCount > 0 || specificReqs.trim().length > 0;

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
          onClick={() => setDismissed(true)}
          style={{
            background: 'none', border: 'none', color: 'var(--text4)',
            fontSize: 16, cursor: 'pointer', lineHeight: 1, padding: '2px 6px',
          }}
          title="Dismiss">
          ×
        </button>
      </div>

      {/* Question cards */}
      <div style={{ padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 500, overflowY: 'auto' }}>
        {questions.map(q => (
          <SchemaQuestionCard
            key={q.id}
            question={q}
            color={color}
            selected={selected[q.id] ?? ''}
            onSelect={val => setSelected(prev => ({ ...prev, [q.id]: val }))}
          />
        ))}

        {/* ── Optional free-text card ── */}
        <div style={{
          background: 'var(--panel)', border: `1px dashed ${color}33`,
          borderRadius: 8, padding: '12px 14px',
        }}>
          <div style={{ fontSize: 11, color: color, fontFamily: "'DM Mono',monospace", letterSpacing: '0.06em', marginBottom: 4 }}>
            SPECIFIC REQUIREMENTS
          </div>
          <div style={{ fontSize: 12.5, color: 'var(--text2)', marginBottom: 10, lineHeight: 1.5 }}>
            Any specific requirements? <span style={{ color: 'var(--text4)', fontSize: 11 }}>(optional)</span>
          </div>
          <textarea
            value={specificReqs}
            onChange={e => setSpecificReqs(e.target.value)}
            placeholder="e.g. Must pass MIL-STD-810G, operating altitude >10,000m, conformal coating required…"
            rows={2}
            style={{
              width: '100%', boxSizing: 'border-box',
              background: 'var(--panel2)', border: `1px solid ${specificReqs.trim() ? color + '55' : color + '22'}`,
              borderRadius: 5, padding: '7px 10px', fontSize: 12,
              color: 'var(--text)', fontFamily: "'DM Mono',monospace",
              outline: 'none', resize: 'vertical', lineHeight: 1.5,
              transition: 'border-color 0.15s',
            }}
          />
        </div>
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
          onClick={() => { onSend(buildReply()); setDismissed(true); }}
          disabled={disabled || !canSend}
          style={{
            padding: '8px 20px', borderRadius: 6,
            background: canSend ? color : 'var(--panel3)',
            color: canSend ? '#070b14' : 'var(--text4)',
            border: 'none', fontSize: 12,
            fontFamily: "'DM Mono',monospace", fontWeight: 700,
            cursor: disabled || !canSend ? 'default' : 'pointer',
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

// ── Clarification-flow types & constants ─────────────────────────────────────
interface ClarificationQuestion { id: string; question: string; why: string; options: string[]; }
interface ClarificationData { intro: string; questions: ClarificationQuestion[]; }
const Q_COLORS_CLARIFY = ['var(--teal)', 'var(--blue)', '#f59e0b', '#8b5cf6', 'var(--teal)'];
const CLARIFY_SUGGESTIONS = [
  { label: 'RF receiver, 5-18GHz wideband', icon: '[RF]' },
  { label: 'BLDC motor controller, 48V, 10kW', icon: '[Motor]' },
  { label: 'FPGA-based digital signal processor', icon: '[FPGA]' },
  { label: 'Power supply, 24V to 5V, 10A', icon: '[Power]' },
];

// ---- Props ----
interface Props {
  project: Project | null;
  phase: PhaseMeta;
  phaseStatus: string;
  pipelineStarted: boolean;
  messages: ChatMessage[];
  onMessages: (msgs: ChatMessage[]) => void;
  onStatusChange: () => void;
  onPhaseComplete: () => void;
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

  // ── Pre-stage clarification flow state ────────────────────────────────────
  type PreStage = 'waiting' | 'loading-clarify' | 'clarifying' | 'done';
  const [preStage, setPreStage] = useState<PreStage>(
    phaseStatus === 'completed' ? 'done' : 'waiting'
  );
  const [requirement, setRequirement] = useState('');
  const [clarification, setClarification] = useState<ClarificationData | null>(null);
  const [clarifyAnswers, setClarifyAnswers] = useState<Record<string, string>>({});
  const [clarifyError, setClarifyError] = useState('');
  const [retryText, setRetryText] = useState('');
  // "Other" option state for clarification cards
  const [otherActiveQId, setOtherActiveQId] = useState<string | null>(null);
  const [otherInputValues, setOtherInputValues] = useState<Record<string, string>>({});
  // Optional free-text field shown after all question cards
  const [clarifySpecificReqs, setClarifySpecificReqs] = useState('');

  // Keep state in sync when props change (e.g. status poll)
  useEffect(() => {
    if (phaseStatus === 'completed') {
      setPhaseCompleted(true);
      setShowApproveCard(true);
    } else if (phaseStatus === 'draft_pending') {
      // User has chatted again after a pipeline run — reset so approve button re-appears
      setShowApproveCard(true);
      setApproveClicked(false);
    } else {
      setShowApproveCard(false);
    }
  }, [phaseStatus]);

  useEffect(() => {
    if (pipelineStarted) setApproveClicked(true);
  }, [pipelineStarted]);

  // Debug: log when showApproveCard changes
  useEffect(() => {
    console.log('[ChatView] showApproveCard changed to:', showApproveCard, 'phaseStatus:', phaseStatus);
  }, [showApproveCard, phaseStatus]);

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
        setPreStage('done'); // skip clarification flow when history exists
      }
    } catch { /* silent */ }
    setHistoryLoaded(true);
  }, [project, historyLoaded, messages.length]);

  useEffect(() => { loadHistory(); }, [loadHistory]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'auto' });
  }, [messages, showApproveCard, phaseCompleted, streaming]);

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
      onMessages([...messages, { role: 'ai', text: '⚠️ Cannot reach the backend server.\n\n**To fix:** Double-click `run.bat` (or `INSTALL.bat` on first use) in the project folder, wait for the "Backend is healthy" message, then try again.\n\nIf already running, check that nothing else is using port 8000.' }]);
      setStreaming('');
      setLoading(false);
    }
  };

  const sendMessage = async (text: string) => {
    if (!project || !text.trim() || loading) return;
    setRetryText(''); // clear any previous retry state on fresh send
    const updated = [...messages, { role: 'user' as const, text }];
    onMessages(updated);
    setInput('');
    setLoading(true);
    setStreaming('');
    // Hide both the approve card and "Pipeline is running" card while user is chatting.
    // They re-appear after the AI responds if the phase is still complete/draft_pending.
    if (showApproveCard) setShowApproveCard(false);

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
          } else if (result.draftPending) {
            // Backend says requirements are captured — show approve button again
            setShowApproveCard(true);
            setApproveClicked(false);
          }
        }
      }, 16);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      const isNetworkErr = !msg.startsWith('HTTP ');
      const display = isNetworkErr
        ? '⚠️ Cannot reach the backend.\n\nDouble-click **run.bat** in the project folder and wait for "Application startup complete", then try again.'
        : `⚠️ Server error — ${msg}\n\nCheck the uvicorn terminal window for the full traceback.`;
      onMessages([...updated, { role: 'ai', text: display }]);
      setStreaming('');
      setLoading(false);
      setRetryText(text); // store so user can retry without re-typing
    }
  };

  const handleRetry = () => {
    if (!retryText) return;
    // Remove the last two messages (failed user bubble + error AI bubble) before retrying
    const trimmed = messages.slice(0, -2);
    onMessages(trimmed);
    sendMessage(retryText);
  };

  // ── Pre-stage clarification handlers ─────────────────────────────────────
  const handleRequirementSubmit = async (req: string) => {
    if (!req.trim() || !project) return;
    setRequirement(req);
    setPreStage('loading-clarify');
    setClarifyError('');
    try {
      const data = await api.clarifyRequirement(
        project.id, req, project.design_type || 'RF'
      );
      setClarification(data);
      setClarifyAnswers({});
      setPreStage('clarifying');
    } catch {
      setClarifyError('Could not load clarification questions. Please try again.');
      setPreStage('waiting');
    }
  };

  const handleClarifyAnswer = (qId: string, opt: string) => {
    setClarifyAnswers(prev => ({ ...prev, [qId]: opt }));
  };

  const allClarifyAnswered =
    clarification !== null &&
    clarification.questions.every(q => clarifyAnswers[q.id] !== undefined);

  const handleConfirmAnswers = () => {
    if (!clarification || !allClarifyAnswered) return;
    const lines = clarification.questions
      .map(q => `${q.question} -> ${clarifyAnswers[q.id]}`)
      .join('\n');
    const extra = clarifySpecificReqs.trim()
      ? `\n\nAdditional requirements: ${clarifySpecificReqs.trim()}`
      : '';
    const fullMessage = `${requirement}\n\n${lines}${extra}`;
    setPreStage('done');
    setInput(''); // Clear the chat input field
    sendMessage(fullMessage);
  };

  // lastAiText intentionally removed — QuickReplyPanel no longer shown in chat flow.

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', position: 'relative' }}>
      {preStage !== 'done' ? (
        /* ── Pre-stage clarification flow ── */
        <>
          <div style={{ flex: 1, overflowY: 'auto', padding: '16px 0 80px' }}>
            {/* waiting: suggestion chips */}
            {preStage === 'waiting' && (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '200px', padding: '32px 16px', gap: 24 }}>
                {clarifyError && (
                  <div style={{ fontSize: 12, color: '#f59e0b', textAlign: 'center' }}>{clarifyError}</div>
                )}
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontFamily: "'Syne',sans-serif", fontSize: 18, fontWeight: 700, color: 'var(--text)', marginBottom: 4 }}>Describe your hardware project</div>
                  <div style={{ fontSize: 11, color: 'var(--text4)', letterSpacing: '0.08em', textTransform: 'uppercase' as const, fontFamily: "'DM Mono',monospace" }}>or pick a quick start</div>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, width: '100%', maxWidth: 480 }}>
                  {CLARIFY_SUGGESTIONS.map(s => (
                    <button key={s.label} onClick={() => handleRequirementSubmit(s.label)}
                      style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: '12px 13px', background: 'var(--panel)', border: `1px solid ${color}22`, borderRadius: 6, cursor: 'pointer', textAlign: 'left' as const, color: 'var(--text2)', fontFamily: "'DM Mono',monospace", fontSize: 12, lineHeight: 1.5 }}
                      onMouseEnter={e => { e.currentTarget.style.borderColor = color; e.currentTarget.style.color = color; }}
                      onMouseLeave={e => { e.currentTarget.style.borderColor = `${color}22`; e.currentTarget.style.color = 'var(--text2)'; }}>
                      <span style={{ fontSize: 14, flexShrink: 0 }}>{s.icon}</span>
                      <span>{s.label}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
            {/* loading-clarify: spinner */}
            {preStage === 'loading-clarify' && (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '200px', gap: 12 }}>
                <div style={{ width: 16, height: 16, border: '2px solid rgba(0,198,167,0.3)', borderTopColor: color, borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
                <span style={{ fontSize: 13, color: 'var(--text3)' }}>Analysing specification...</span>
              </div>
            )}
            {/* clarifying: question cards */}
            {preStage === 'clarifying' && clarification && (
              <div style={{ padding: '0 4px' }}>
                <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 14 }}>
                  <div style={{ background: `${color}18`, border: `1px solid ${color}33`, borderRadius: '8px 8px 2px 8px', padding: '9px 13px', maxWidth: '80%', fontSize: 13, color: 'var(--text)', lineHeight: 1.5, fontFamily: "'DM Mono',monospace" }}>
                    {requirement}
                  </div>
                </div>
                <div style={{ fontSize: 13, color: 'var(--text2)', lineHeight: 1.6, marginBottom: 16 }}>
                  {clarification.intro}
                </div>
                {clarification.questions.map((q, qi) => {
                  const qColor = Q_COLORS_CLARIFY[qi % Q_COLORS_CLARIFY.length];
                  const sel = clarifyAnswers[q.id];
                  return (
                    <div key={q.id} style={{ marginBottom: 18 }}>
                      <div style={{ fontSize: 10, color: qColor, letterSpacing: '0.1em', textTransform: 'uppercase' as const, fontWeight: 600, fontFamily: "'DM Mono',monospace", marginBottom: 4 }}>
                        Q{qi + 1} &middot; {q.why}
                      </div>
                      <div style={{ fontSize: 13, color: 'var(--text)', lineHeight: 1.5, marginBottom: 9 }}>
                        {q.question}
                      </div>
                      <div style={{ display: 'flex', flexWrap: 'wrap' as const, gap: 7 }}>
                        {q.options.map(opt => {
                          const isSel = sel === opt;
                          return (
                            <button key={opt} onClick={() => { handleClarifyAnswer(q.id, opt); setOtherActiveQId(null); }}
                              style={{ padding: '6px 13px', fontSize: 12, fontFamily: "'DM Mono',monospace", background: isSel ? `${qColor}22` : 'var(--panel)', border: `0.5px solid ${isSel ? qColor : qColor + '44'}`, borderRadius: 4, cursor: 'pointer', color: isSel ? 'var(--text)' : 'var(--text3)', transition: 'all 0.12s' }}
                              onMouseEnter={e => { if (!isSel) { e.currentTarget.style.borderColor = qColor; e.currentTarget.style.color = 'var(--text)'; } }}
                              onMouseLeave={e => { if (!isSel) { e.currentTarget.style.borderColor = qColor + '44'; e.currentTarget.style.color = 'var(--text3)'; } }}>
                              {isSel ? '\u2713 ' : ''}{opt}
                            </button>
                          );
                        })}
                        {/* "Other" option — always visible */}
                        {otherActiveQId !== q.id ? (
                          <button
                            onClick={() => { setOtherActiveQId(q.id); }}
                            style={{ padding: '6px 13px', fontSize: 12, fontFamily: "'DM Mono',monospace", background: (sel && !q.options.includes(sel)) ? `${qColor}22` : 'var(--panel)', border: `0.5px solid ${(sel && !q.options.includes(sel)) ? qColor : qColor + '44'}`, borderRadius: 4, cursor: 'pointer', color: (sel && !q.options.includes(sel)) ? 'var(--text)' : 'var(--text3)', transition: 'all 0.12s' }}
                            onMouseEnter={e => { e.currentTarget.style.borderColor = qColor; e.currentTarget.style.color = 'var(--text)'; }}
                            onMouseLeave={e => { if (!(sel && !q.options.includes(sel))) { e.currentTarget.style.borderColor = qColor + '44'; e.currentTarget.style.color = 'var(--text3)'; } }}>
                            {(sel && !q.options.includes(sel)) ? `\u2713 ${sel}` : '✏ Other'}
                          </button>
                        ) : (
                          <div style={{ display: 'flex', gap: 6, width: '100%', marginTop: 4 }}>
                            <input
                              autoFocus
                              value={otherInputValues[q.id] || ''}
                              onChange={e => setOtherInputValues(prev => ({ ...prev, [q.id]: e.target.value }))}
                              onKeyDown={e => {
                                if (e.key === 'Enter' && (otherInputValues[q.id] || '').trim()) {
                                  handleClarifyAnswer(q.id, otherInputValues[q.id].trim());
                                  setOtherActiveQId(null);
                                } else if (e.key === 'Escape') {
                                  setOtherActiveQId(null);
                                }
                              }}
                              placeholder="Type your answer..."
                              style={{ flex: 1, background: 'var(--panel)', border: `1px solid ${qColor}66`, borderRadius: 4, padding: '5px 10px', fontSize: 12, color: 'var(--text)', fontFamily: "'DM Mono',monospace", outline: 'none' }}
                            />
                            <button
                              disabled={!(otherInputValues[q.id] || '').trim()}
                              onClick={() => { if ((otherInputValues[q.id] || '').trim()) { handleClarifyAnswer(q.id, otherInputValues[q.id].trim()); setOtherActiveQId(null); } }}
                              style={{ padding: '5px 12px', fontSize: 11, background: (otherInputValues[q.id] || '').trim() ? qColor : 'var(--panel2)', border: 'none', borderRadius: 4, cursor: (otherInputValues[q.id] || '').trim() ? 'pointer' : 'default', color: (otherInputValues[q.id] || '').trim() ? '#070b14' : 'var(--text4)', fontFamily: "'DM Mono',monospace", fontWeight: 700 }}>
                              OK
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
                {allClarifyAnswered && (
                  <>
                    {/* Optional free-text card */}
                    <div style={{ marginBottom: 18, marginTop: 4 }}>
                      <div style={{ fontSize: 10, color: 'var(--text4)', letterSpacing: '0.1em', textTransform: 'uppercase' as const, fontWeight: 600, fontFamily: "'DM Mono',monospace", marginBottom: 4 }}>
                        ANY SPECIFIC REQUIREMENTS? <span style={{ opacity: 0.6, textTransform: 'none' as const, letterSpacing: 0, fontWeight: 400 }}>optional</span>
                      </div>
                      <textarea
                        value={clarifySpecificReqs}
                        onChange={e => setClarifySpecificReqs(e.target.value)}
                        placeholder="e.g. Must operate at -40\xB0C to +85\xB0C, use SMA connectors, IPC Class 3..."
                        rows={3}
                        style={{ width: '100%', background: 'var(--panel)', border: `1px solid ${clarifySpecificReqs.trim() ? color + '66' : 'var(--panel3)'}`, borderRadius: 5, padding: '9px 12px', fontSize: 12, color: 'var(--text)', fontFamily: "'DM Mono',monospace", resize: 'vertical' as const, outline: 'none', lineHeight: 1.65, boxSizing: 'border-box' as const, transition: 'border-color 0.2s' }}
                        onFocus={e => { e.target.style.borderColor = color + '99'; }}
                        onBlur={e => { e.target.style.borderColor = clarifySpecificReqs.trim() ? color + '66' : 'var(--panel3)'; }}
                      />
                    </div>
                    <div style={{ paddingBottom: 16 }}>
                      <button onClick={handleConfirmAnswers}
                        style={{ width: '100%', padding: '11px 0', background: `${color}12`, border: `0.5px solid ${color}80`, borderRadius: 4, color, fontSize: 13, fontFamily: "'DM Mono',monospace", cursor: 'pointer', letterSpacing: '0.02em' }}>
                        Generate requirements spec &rarr;
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}
            <div ref={bottomRef} />
          </div>
          {preStage === 'waiting' && (
            <div style={{ position: 'sticky', bottom: 0, left: 0, right: 0, background: 'linear-gradient(transparent, var(--navy) 20%)', padding: '16px 0 4px' }}>
              <div style={{ display: 'flex', gap: 8 }}>
                <textarea
                  value={requirement}
                  onChange={e => setRequirement(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleRequirementSubmit(requirement); } }}
                  placeholder="Type your hardware requirement..."
                  rows={1}
                  style={{ flex: 1, background: 'var(--panel)', border: '1px solid var(--panel3)', borderRadius: 6, padding: '11px 14px', fontSize: 13, color: 'var(--text)', fontFamily: "'DM Mono',monospace", resize: 'none' as const, outline: 'none', lineHeight: 1.5, transition: 'border-color 0.2s' }}
                  onFocus={e => { e.target.style.borderColor = color; }}
                  onBlur={e => { e.target.style.borderColor = 'var(--panel3)'; }}
                />
                <button
                  onClick={() => handleRequirementSubmit(requirement)}
                  disabled={!requirement.trim()}
                  style={{ padding: '0 18px', borderRadius: 6, cursor: requirement.trim() ? 'pointer' : 'default', fontSize: 12, fontFamily: "'DM Mono',monospace", fontWeight: 700, background: requirement.trim() ? color : 'var(--panel2)', border: 'none', color: requirement.trim() ? '#070b14' : 'var(--text4)', transition: 'all 0.15s', whiteSpace: 'nowrap' as const }}>
                  Send &rarr;
                </button>
              </div>
            </div>
          )}
          <style>{`@keyframes spin { to { transform: rotate(360deg); } } @keyframes blink { 50% { opacity: 0; } } @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }`}</style>
        </>
      ) : (
        /* ── Chat flow ── */
        <>
          {/* Scrollable messages area */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '4px 0 80px 0' }}>
            {/* Welcome card — show only when no messages */}
            {messages.length === 0 && !loading && (
              <WelcomeCard color={color} onSuggestion={sendMessage} />
            )}

        {/* Message history */}
        {messages.map((msg, i) => (
          <ChatMessageItem key={i} msg={msg} color={color} />
        ))}

        {/* QuickReplyPanel removed — clarification is handled by the pre-stage flow
            before the first message. Users type freely after that. */}

        {/* Streaming / loading indicator */}
        {(loading || streaming) && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ padding: '14px 18px', borderRadius: 8, background: 'var(--panel2)', border: '1px solid var(--panel3)' }}>
              <div style={{ fontSize: 10, color, marginBottom: 8, letterSpacing: '0.1em' }}>AI RESPONSE</div>
              {streaming ? (
                <div style={{ fontSize: 13, color: 'var(--text2)', lineHeight: 1.65, whiteSpace: 'pre-wrap', fontFamily: "'DM Mono',monospace" }}>
                  {streaming}
                  <span style={{ display: 'inline-block', width: 7, height: 14, background: color, marginLeft: 2, animation: 'blink 1s step-end infinite' }} />
                </div>
              ) : (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={{ width: 8, height: 8, borderRadius: '50%', background: color, animation: 'pulse 1s ease-in-out infinite' }} />
                  <span style={{ fontSize: 12, color: 'var(--text3)' }}>Thinking...</span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Approve & Run card */}
        {showApproveCard && !approveClicked && (
          <div style={{
            background: `${color}0d`, border: `1px solid ${color}33`,
            borderRadius: 10, padding: '16px 20px', marginBottom: 16,
          }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)', marginBottom: 8 }}>
              Requirements captured! Ready to run the full pipeline?
            </div>
            <div style={{ fontSize: 12, color: 'var(--text3)', marginBottom: 12 }}>
              This will generate HRS, compliance matrix, netlist, GLR, SRS, SDD, and code review.
            </div>
            <button
              onClick={() => { setApproveClicked(true); onPhaseComplete(); }}
              style={{
                padding: '10px 24px', borderRadius: 6, cursor: 'pointer',
                fontSize: 13, fontFamily: "'DM Mono', monospace", fontWeight: 700,
                background: color, border: 'none', color: '#070b14',
                boxShadow: `0 0 20px ${color}40`, transition: 'all 0.2s',
              }}>
              Approve &amp; Run Pipeline →
            </button>
          </div>
        )}

        {/* Pipeline running card */}
        {showApproveCard && approveClicked && (
          <div style={{
            background: `${color}0d`, border: `1px solid ${color}22`,
            borderRadius: 10, padding: '14px 18px', marginBottom: 16,
            display: 'flex', alignItems: 'center', gap: 10,
          }}>
            <div style={{ width: 10, height: 10, borderRadius: '50%', background: color, animation: 'pulse 1s ease-in-out infinite' }} />
            <span style={{ fontSize: 12, color: 'var(--text2)' }}>
              Pipeline is running — check <strong style={{ color }}>Documents</strong> tab for generated outputs
            </span>
          </div>
        )}

        {/* Retry button — shown when last send failed (network / server error) */}
        {retryText && !loading && (
          <div style={{ textAlign: 'center', marginBottom: 12 }}>
            <button
              onClick={handleRetry}
              style={{
                padding: '9px 22px', borderRadius: 6, cursor: 'pointer',
                fontSize: 12, fontFamily: "'DM Mono', monospace", fontWeight: 700,
                background: `${color}18`, border: `1px solid ${color}66`,
                color, transition: 'all 0.15s',
              }}>
              ↺ Retry last message
            </button>
          </div>
        )}

        {/* Generate Documents button — only before approval */}
        {!phaseCompleted && messages.length >= 2 && !loading && (
          <div style={{ textAlign: 'center', marginBottom: 16 }}>
            <button
              onClick={finalizePhase}
              style={{
                padding: '10px 24px', borderRadius: 6, cursor: 'pointer',
                fontSize: 12, fontFamily: "'DM Mono', monospace", fontWeight: 600,
                background: 'transparent', border: `1px solid ${color}55`,
                color, transition: 'all 0.15s',
              }}
              onMouseEnter={e => { e.currentTarget.style.background = `${color}18`; }}
              onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; }}>
              Generate Documents →
            </button>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Sticky input area */}
      <div style={{
        position: 'sticky', bottom: 0, left: 0, right: 0,
        background: 'linear-gradient(transparent, var(--navy) 20%)',
        padding: '16px 0 4px',
      }}>
        <div style={{ display: 'flex', gap: 8 }}>
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(input); } }}
            placeholder="Describe your hardware requirement or ask anything..."
            rows={1}
            style={{
              flex: 1, background: 'var(--panel)', border: `1px solid var(--panel3)`,
              borderRadius: 6, padding: '11px 14px', fontSize: 13,
              color: 'var(--text)', fontFamily: "'DM Mono', monospace",
              resize: 'none', outline: 'none', lineHeight: 1.5,
              transition: 'border-color 0.2s',
            }}
            onFocus={e => { e.target.style.borderColor = color; }}
            onBlur={e => { e.target.style.borderColor = 'var(--panel3)'; }}
          />
          <button
            onClick={() => sendMessage(input)}
            disabled={!input.trim() || loading}
            style={{
              padding: '0 18px', borderRadius: 6, cursor: input.trim() && !loading ? 'pointer' : 'default',
              fontSize: 12, fontFamily: "'DM Mono', monospace", fontWeight: 700,
              background: input.trim() && !loading ? color : 'var(--panel2)',
              border: 'none',
              color: input.trim() && !loading ? '#070b14' : 'var(--text4)',
              transition: 'all 0.15s', whiteSpace: 'nowrap',
            }}>
            Send →
          </button>
        </div>
      </div>

      <style>{`
        @keyframes blink { 50% { opacity: 0; } }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
      `}</style>
        </>
      )}
    </div>
  );
}
            Send