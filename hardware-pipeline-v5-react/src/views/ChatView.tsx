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
