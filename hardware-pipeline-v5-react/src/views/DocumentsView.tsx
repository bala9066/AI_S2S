import { useState, useEffect, useRef, useCallback } from 'react';
import { marked } from 'marked';
import type { Project, PhaseMeta, PhaseStatusValue } from '../types';
import { api } from '../api';
import { getVisibleDocuments } from '../data/phases';
import { loadMermaid, renderMermaid, purgeMermaidScratch } from '../utils/mermaid';

interface DocFile {
  name: string;
  size: number;
}

interface Props {
  project: Project | null;
  phase: PhaseMeta;
  status: PhaseStatusValue;
  pipelineRunning?: boolean;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function getExt(name: string): string {
  const dot = name.lastIndexOf('.');
  return dot >= 0 ? name.slice(dot + 1).toLowerCase() : '';
}

const EXT_COLOR: Record<string, string> = {
  md: '#00c6a7', docx: '#3b82f6', pdf: '#f59e0b',
  json: '#f59e0b', net: '#8b5cf6', txt: '#94a3b8',
  html: '#f59e0b', csv: '#10b981', xdc: '#8b5cf6',
  py: '#3b82f6', c: '#00c6a7', h: '#94a3b8', cpp: '#00c6a7',
};

const EXT_LABEL: Record<string, string> = {
  md: 'Markdown', docx: 'Word Doc', pdf: 'PDF',
  json: 'JSON', net: 'Netlist', txt: 'Text',
  html: 'HTML', csv: 'CSV', xdc: 'Constraints',
  py: 'Python', c: 'C Source', h: 'C Header', cpp: 'C++ Source',
};

function extColor(ext: string): string { return EXT_COLOR[ext] || '#64748b'; }
function extLabel(ext: string): string { return EXT_LABEL[ext] || ext.toUpperCase(); }

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const VIEWABLE = new Set(['md', 'txt', 'json', 'html', 'csv', 'net', 'xdc', 'py', 'c', 'h', 'cpp']);

// ── Mermaid sanitization ──────────────────────────────────────────────────────

function sanitizeMermaidCode(raw: string): string {
  let code = raw.trim().replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  // Normalise graph → flowchart
  code = code.replace(/^graph\s+(TD|LR|TB|RL|BT)/im, 'flowchart $1');
  // Step 0: join lines where [ is opened but not closed.
  // LLMs split node labels across lines (e.g. SINK[Heatsink\n  AIR[...]]),
  // which places the "end" subgraph keyword inside what looks like a label body,
  // causing "got 'STR'" parse errors.
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
  // Replace literal \n escape sequences with Mermaid HTML line-break
  // LLMs often emit \n inside labels thinking it's a newline escape
  code = code.replace(/\\n/g, '<br/>');
  // Decode HTML entities that agents mistakenly encode in Mermaid source
  // e.g. &lt;br/&gt; → <br/>,  &lt;  → < (will be re-sanitized below)
  code = code.replace(/&lt;br\s*\/?&gt;/gi, '<br/>');
  code = code.replace(/&lt;/g, '<').replace(/&gt;/g, '>');
  // Strip HTML tags (except <br/>) from the whole diagram body
  code = code.replace(/<(?!br\s*\/?)[^>]+>/gi, ' ');
  // Fix: "PSU [+28V Input]" → "PSU[+28V Input]" — space before bracket breaks Mermaid parser
  // Apply only to non-subgraph lines (subgraph has intentional spaces).
  code = code.split('\n').map(line => {
    if (/^\s*subgraph\b/.test(line)) return line; // don't touch subgraph declarations
    // Replace word-char + space + [ with word-char + [ (node ID parsing fix)
    return line.replace(/(\w)\s+\[/g, '$1[');
  }).join('\n');

  // Sanitize flowchart node labels: [ ... ], ( ... ), { ... }
  // Preserve <br/> for multi-line labels; neutralise other angle-bracket chars.
  const sanitizeLabel = (inner: string) =>
    inner
      // protect <br/> tokens before we touch angle brackets
      .replace(/<br\s*\/?>/gi, '\x00BR\x00')
      .replace(/&(?!amp;|lt;|gt;|#)/g, 'and')
      .replace(/</g, '(')   // convert bare < to ( so Mermaid doesn't choke
      .replace(/>/g, ')')   // convert bare > to )
      // restore <br/>
      .replace(/\x00BR\x00/g, '<br/>');
  code = code.replace(/\[([^\]]*)\]/g, (_m, inner: string) => `[${sanitizeLabel(inner)}]`);
  code = code.replace(/\(([^)]*)\)/g, (_m, inner: string) => `(${sanitizeLabel(inner)})`);
  code = code.replace(/\{([^}]*)\}/g, (_m, inner: string) => `{${sanitizeLabel(inner)}}`);
  // Sanitize state diagram transition labels (after '-->...:'): remove > < and extra colons
  if (first.startsWith('statediagram')) {
    code = code.split('\n').map(line => {
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

// ── Marked setup ──────────────────────────────────────────────────────────────

marked.setOptions({ gfm: true, breaks: false });

// ── MermaidBlock component ────────────────────────────────────────────────────

// Inject CSS overrides into the SVG so it always looks right regardless of
// which Mermaid version is loaded from CDN.
function patchSvg(raw: string, accentColor: string): string {
  // Make SVG fluid-width so it fills the container on all screen sizes
  let s = raw
    .replace(/<svg([^>]*)width="[^"]*"/, '<svg$1width="100%"')
    .replace(/<svg([^>]*)height="([^"]*)"/, '<svg$1height="auto" data-orig-height="$2"')
    .replace(/<svg(?![^>]*style=)([^>]*)>/, '<svg$1 style="max-width:100%;display:block;">');

  // Append our CSS overrides before </style> (or inject a new <style> block)
  const overrideCss = `
    /* Hardware Pipeline — Mermaid visual overrides */
    svg { background: #0f1e33 !important; }
    .node rect, .node circle, .node ellipse, .node polygon, .node path {
      fill: #1a2235 !important;
      stroke: ${accentColor} !important; stroke-width: 1.5px !important;
      rx: 6; ry: 6;
    }
    .edgePath .path { stroke: ${accentColor} !important; stroke-width: 1.5px !important; }
    .arrowheadPath { fill: ${accentColor} !important; stroke: none !important; }
    .edgeLabel .label rect { fill: #0f1e33 !important; }
    .edgeLabel .label span, .edgeLabel span { color: #e2e8f0 !important; font-size: 11px !important; }
    .cluster rect { fill: #0d1423 !important; stroke: #2a3a50 !important; stroke-width: 1px !important; rx: 8; ry: 8; }
    .cluster text, .cluster tspan, .cluster span { fill: #94a3b8 !important; font-size: 11px !important; font-weight: 600 !important; letter-spacing: 0.06em !important; }
    text, tspan { fill: #e2e8f0 !important; font-family: 'DM Mono', monospace !important; font-size: 12px !important; }
    .nodeLabel, .label, .label span, .labelText { color: #e2e8f0 !important; fill: #e2e8f0 !important; font-size: 12px !important; }
    .nodeLabel p { margin: 0 !important; color: #e2e8f0 !important; }
    foreignObject div, foreignObject span, foreignObject p { color: #e2e8f0 !important; font-size: 12px !important; font-family: 'DM Mono', monospace !important; }
    .messageText, .actor text, .note text, .labelBox text { fill: #e2e8f0 !important; }
    .actor rect, .actor line { fill: #1a2235 !important; stroke: ${accentColor} !important; }
    .messageLine0, .messageLine1 { stroke: ${accentColor} !important; }
    .activation0, .activation1, .activation2 { fill: #2a3a50 !important; stroke: ${accentColor} !important; }
    .loopLine { stroke: #2a3a50 !important; }
    .loopText, .loopText tspan { fill: #94a3b8 !important; }
    .noteText, .noteText tspan { fill: #e2e8f0 !important; }
    .note { fill: #1a2235 !important; stroke: #2a3a50 !important; }
  `;

  if (s.includes('</style>')) {
    s = s.replace('</style>', overrideCss + '</style>');
  } else {
    s = s.replace('<svg', `<svg><style>${overrideCss}</style><svg`).replace('<svg><style>', '<svg><style>');
    // simpler: just prepend a style block inside the <svg>
    s = s.replace(/(<svg[^>]*>)/, `$1<style>${overrideCss}</style>`);
  }
  return s;
}

function MermaidBlock({ code, color }: { code: string; color: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [svg, setSvg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const id = useRef(`mmd-${Math.random().toString(36).slice(2)}`);

  useEffect(() => {
    let cancelled = false;
    const rid = id.current;

    // 12-second timeout — if mermaid hangs (invalid syntax), show fallback
    const timeout = setTimeout(() => {
      if (!cancelled) {
        cancelled = true;
        purgeMermaidScratch(rid);
        setErr('Diagram render timed out — showing source');
      }
    }, 12000);

    (async () => {
      try {
        await loadMermaid(); // instant — mermaid is bundled, not CDN
        const rawSvg = await renderMermaid(rid, code);
        clearTimeout(timeout);
        purgeMermaidScratch(rid);
        if (!cancelled) {
          if (rawSvg?.includes('<svg') && !rawSvg.includes('class="error"')) {
            setSvg(patchSvg(rawSvg, color));
          } else {
            setErr('Diagram produced no SVG output');
          }
        }
      } catch (e: unknown) {
        clearTimeout(timeout);
        purgeMermaidScratch(rid);
        if (!cancelled) {
          const msg = e instanceof Error ? e.message : String(e);
          setErr(`Syntax error: ${msg.slice(0, 120)}`);
        }
      }
    })();

    return () => {
      cancelled = true;
      clearTimeout(timeout);
      purgeMermaidScratch(rid);
    };
  }, [code]);

  if (err) {
    // Graceful fallback: show the raw Mermaid source with the error reason
    return (
      <div style={{ margin: '4px 0' }}>
        <div style={{ fontSize: 10, color: '#f59e0b', fontFamily: "'DM Mono', monospace", letterSpacing: '0.08em', marginBottom: 5 }}>
          ⚠ DIAGRAM SOURCE — {err}
        </div>
        <pre style={{
          background: 'var(--panel2)', border: '1px solid rgba(245,158,11,0.25)', borderRadius: 6,
          padding: '12px 14px', margin: 0, fontSize: 11, color: 'var(--text3)',
          fontFamily: "'JetBrains Mono', monospace",
          overflowX: 'auto', lineHeight: 1.65, whiteSpace: 'pre-wrap',
        }}>
          {code}
        </pre>
      </div>
    );
  }
  if (!svg) {
    return (
      <div style={{ padding: '14px', display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text4)', fontSize: 12 }}>
        <div style={{ width: 12, height: 12, borderRadius: '50%', border: `2px solid ${color}`, borderTopColor: 'transparent', animation: 'spin 0.8s linear infinite' }} />
        Rendering diagram...
      </div>
    );
  }
  return (
    <div ref={ref}
      style={{
        padding: '20px 16px',
        overflowX: 'auto',
        background: '#0a1628',
        borderRadius: 8,
        border: `1px solid ${color}30`,
        boxShadow: `0 0 32px rgba(0,0,0,0.4), inset 0 0 60px rgba(0,0,0,0.2)`,
      }}
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}

// ── MarkdownRenderer ──────────────────────────────────────────────────────────

function MarkdownRenderer({ content, color }: { content: string; color: string }) {
  const parts: Array<{ type: 'md' | 'mermaid'; text: string }> = [];
  // Normalise Windows line endings so the regex works regardless of how the
  // file was written (Python on Windows produces \r\n in write_text())
  const normalised = content.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

  // Match ```mermaid or any code block whose first non-blank line starts with
  // a known Mermaid diagram type (handles agents that omit the language tag).
  const MERMAID_TYPES = /^(flowchart|graph|sequencediagram|classdiagram|statediagram|erdiagram|gantt|pie\s|gitgraph|mindmap|timeline)/i;
  // Regex captures: group 1 = optional lang tag (e.g. "mermaid"), group 2 = code body
  const mermaidRe = /```([a-z]*)[ \t]*\n([\s\S]*?)```/gi;
  let lastIdx = 0;
  let m: RegExpExecArray | null;

  while ((m = mermaidRe.exec(normalised)) !== null) {
    const lang = m[1].toLowerCase();
    const body = m[2];
    const firstLine = body.trimStart().split('\n')[0].trim();
    // Accept if language tag is "mermaid" OR the code body starts with a known Mermaid type
    const isMermaid = lang === 'mermaid' || (lang === '' && MERMAID_TYPES.test(firstLine));
    if (!isMermaid) {
      // Not a mermaid block — keep as markdown (include the full fenced block)
      if (m.index > lastIdx) parts.push({ type: 'md', text: normalised.slice(lastIdx, m.index) });
      parts.push({ type: 'md', text: m[0] });
      lastIdx = m.index + m[0].length;
      continue;
    }
    if (m.index > lastIdx) parts.push({ type: 'md', text: normalised.slice(lastIdx, m.index) });
    // Run full sanitization: strip HTML, fix \n escapes, escape > < in labels
    const cleanCode = sanitizeMermaidCode(body);
    parts.push({ type: 'mermaid', text: cleanCode });
    lastIdx = m.index + m[0].length;
  }
  if (lastIdx < normalised.length) parts.push({ type: 'md', text: normalised.slice(lastIdx) });

  return (
    <div style={{ padding: '22px 26px', lineHeight: 1.75 }}>
      {parts.map((part, i) => {
        if (part.type === 'mermaid') {
          return (
            <div key={i} style={{ margin: '18px 0' }}>
              <div style={{ fontSize: 10, color: 'var(--text4)', fontFamily: "'DM Mono', monospace", marginBottom: 8, letterSpacing: '0.1em' }}>DIAGRAM</div>
              <MermaidBlock code={part.text} color={color} />
            </div>
          );
        }
        const html = marked.parse(part.text) as string;
        return <div key={i} className="md-body" dangerouslySetInnerHTML={{ __html: html }} />;
      })}
    </div>
  );
}

// ── FileIcon ──────────────────────────────────────────────────────────────────

function FileIcon({ ext, color }: { ext: string; color: string }) {
  const icons: Record<string, string> = {
    md: '📝', docx: '📄', pdf: '📋', json: '{ }', net: '⬡', txt: '📃',
    html: '</>', csv: '⊞', xdc: '◈',
  };
  const icon = icons[ext] || '📄';
  return (
    <div style={{
      width: 40, height: 40, borderRadius: 8, flexShrink: 0,
      background: `${color}12`, border: `1px solid ${color}28`,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: ext === 'json' ? 11 : ext === 'html' || ext === 'xdc' ? 12 : 18,
      color: ['json', 'html', 'xdc', 'net'].includes(ext) ? color : undefined,
      fontFamily: ['json', 'html', 'xdc', 'net'].includes(ext) ? "'JetBrains Mono', monospace" : undefined,
      fontWeight: 700,
    }}>
      {icon}
    </div>
  );
}

// ── PhaseDetails component — shows inputs/outputs/tools/metrics ───────────────

function PhaseDetails({ phase, color, collapsed = false }: { phase: PhaseMeta; color: string; collapsed?: boolean }) {
  const [open, setOpen] = useState(!collapsed);

  const Section = ({ title, items }: { title: string; items: string[] }) => (
    <div style={{ marginBottom: 14 }}>
      <div style={{ fontSize: 10, color, letterSpacing: '0.1em', fontFamily: "'DM Mono',monospace", marginBottom: 6 }}>{title}</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {items.map((item, i) => (
          <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
            <span style={{ color: `${color}80`, fontSize: 9, marginTop: 4, flexShrink: 0 }}>▸</span>
            <span style={{ fontSize: 12, color: 'var(--text3)', lineHeight: 1.5 }}>{item}</span>
          </div>
        ))}
      </div>
    </div>
  );

  const m = phase.metrics;

  return (
    <div style={{ border: `1px solid ${color}18`, borderRadius: 8, overflow: 'hidden', marginBottom: 16 }}>
      {/* Header row — always visible */}
      <div
        onClick={() => setOpen(v => !v)}
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '10px 14px', cursor: 'pointer', background: `${color}06`,
          borderBottom: open ? `1px solid ${color}18` : 'none',
        }}
      >
        <div style={{ fontSize: 11, color, letterSpacing: '0.08em', fontFamily: "'DM Mono',monospace" }}>
          ◈ PHASE DETAILS — {phase.code} {phase.name.toUpperCase()}
        </div>
        <span style={{ fontSize: 11, color: 'var(--text4)' }}>{open ? '▲' : '▼'}</span>
      </div>

      {open && (
        <div style={{ padding: '16px 18px' }}>
          {/* Metrics row */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, marginBottom: 16 }}>
            {[
              { label: 'TIME SAVED', value: m.timeSaved },
              { label: 'ERROR REDUCTION', value: m.errorReduction },
              { label: 'CONFIDENCE', value: m.confidence },
              { label: 'COST IMPACT', value: m.costImpact },
            ].map(({ label, value }) => (
              <div key={label} style={{ background: `${color}08`, border: `1px solid ${color}18`, borderRadius: 6, padding: '8px 10px' }}>
                <div style={{ fontSize: 9, color: 'var(--text4)', letterSpacing: '0.1em', marginBottom: 4, fontFamily: "'DM Mono',monospace" }}>{label}</div>
                <div style={{ fontSize: 12, color, fontWeight: 700 }}>{value}</div>
              </div>
            ))}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16 }}>
            <Section title="INPUTS" items={phase.inputs} />
            <Section title="OUTPUTS" items={phase.outputs} />
            <Section title="TOOLS" items={phase.tools} />
          </div>
        </div>
      )}
    </div>
  );
}

// ── GeneratingState — shown when phase is in_progress but no files yet ─────────

function GeneratingState({ phase }: { phase: PhaseMeta }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setElapsed(s => s + 1), 1000);
    return () => clearInterval(t);
  }, []);

  const mins = Math.floor(elapsed / 60);
  const secs = elapsed % 60;
  const elapsedStr = mins > 0
    ? `${mins}m ${secs.toString().padStart(2, '0')}s`
    : `${secs}s`;

  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, marginBottom: 12 }}>
        <div style={{ width: 14, height: 14, borderRadius: '50%', border: `2.5px solid ${phase.color}`, borderTopColor: 'transparent', animation: 'spin 0.8s linear infinite' }} />
        <div style={{ fontSize: 14, color: phase.color, fontWeight: 600 }}>AI agent running — generating documents...</div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 20, marginBottom: 12 }}>
        <div style={{ fontSize: 12, color: 'var(--text4)', fontFamily: "'DM Mono', monospace" }}>
          Elapsed: <span style={{ color: phase.color }}>{elapsedStr}</span>
        </div>
        <div style={{ fontSize: 12, color: 'var(--text4)', fontFamily: "'DM Mono', monospace" }}>
          Estimated: <span style={{ color: phase.color }}>{phase.time}</span>
        </div>
      </div>
      <div style={{ fontSize: 12, color: 'var(--text4)', maxWidth: 380, margin: '0 auto', lineHeight: 1.7 }}>
        Output files will appear here automatically once the phase completes.
      </div>
    </>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function DocumentsView({ project, phase, status, pipelineRunning }: Props) {
  const [files, setFiles] = useState<DocFile[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  // Track which phase IDs have been loaded at least once — prevents spinner on phase re-visit
  const loadedPhaseIds = useRef<Set<string>>(new Set());
  // Track if we've ever successfully fetched any files — once true, phase switches are always silent
  const hasAnyFiles = useRef(false);
  // Track previous status to detect transitions (in_progress → completed/failed)
  const prevStatusRef = useRef<string>(status);
  const [contents, setContents] = useState<Record<string, string>>({});
  const [expanded, setExpanded] = useState<string | null>(null);
  const [loadingFile, setLoadingFile] = useState<Record<string, boolean>>({});
  const [docxConverting, setDocxConverting] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);

  const visibleFilenames = project
    ? new Set(getVisibleDocuments(phase.id, project.name))
    : new Set<string>();

  // Pipeline-internal JSON files are kept on disk for agent use but hidden from the UI.
  // Human-readable equivalents (netlist_visual.md, sbom_summary.md) cover them.
  const HIDDEN_FILES = new Set(['netlist.json', 'netlist_validation.json', 'sbom.json']);
  const filteredFiles = files.filter(f =>
    visibleFilenames.has(f.name) && !HIDDEN_FILES.has(f.name)
  );

  const fetchList = useCallback((silent = false, currentPhaseId?: string) => {
    if (!project) return;
    if (!silent) { setLoadingList(true); setError(null); }

    // Timeout: if loading takes >8s, force-complete to avoid permanent spinner
    let timedOut = false;
    const timeout = !silent ? setTimeout(() => {
      timedOut = true;
      setLoadingList(false);
    }, 8000) : undefined;

    api.listDocuments(project.id)
      .then(list => {
        if (timeout) clearTimeout(timeout);
        if (timedOut) return;
        setFiles(list);
        setLoadingList(false);
        if (list.length > 0) hasAnyFiles.current = true;
        if (currentPhaseId) loadedPhaseIds.current.add(currentPhaseId);
      })
      .catch((err: Error) => {
        if (timeout) clearTimeout(timeout);
        if (timedOut) return;
        const msg = err?.message || 'Unknown error';
        if (!silent) {
          if (msg.includes('HTTP 404')) setError('Documents endpoint not found (HTTP 404). Restart the backend.');
          else if (msg.includes('HTTP 500')) setError('Server error (HTTP 500): ' + msg);
          else if (msg.includes('HTTP 405')) setError('Method not allowed (HTTP 405). Restart the backend.');
          else setError('API error: ' + msg);
        }
        setLoadingList(false);
      });
  }, [project]);

  // Load documents when project or phase changes.
  // Show spinner only on the very first project load when no files exist yet.
  // Once any files have been fetched (hasAnyFiles), all phase switches are silent
  // so cached data shows instantly while the list refreshes in the background.
  useEffect(() => {
    const alreadyLoaded = loadedPhaseIds.current.has(phase.id);
    // Silent if: visited this phase before, OR any files ever loaded (project-wide cache exists)
    // BUG FIX: was fetchList(!silent) — the ! inverted the logic so already-loaded phases
    // showed the spinner and first-load phases skipped it. Correct: pass silent directly.
    const silent = alreadyLoaded || hasAnyFiles.current;
    fetchList(silent, phase.id);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project, phase.id]);

  // Periodic refresh while phase is running
  useEffect(() => {
    const shouldRefresh = pipelineRunning || status === 'in_progress';
    if (!project || !shouldRefresh) return;
    const interval = setInterval(() => fetchList(true), 3000);
    return () => clearInterval(interval);
  }, [project, pipelineRunning, status, fetchList]);

  // Critical: when a phase transitions from in_progress → completed/failed,
  // do immediate re-fetches to catch files written in the final moments.
  // Without this, the file list may be stale if the last periodic poll happened
  // just before the backend flushed output files, leaving the spinner permanently.
  useEffect(() => {
    const prev = prevStatusRef.current;
    prevStatusRef.current = status;
    if (prev === 'in_progress' && (status === 'completed' || status === 'failed')) {
      // Immediate fetch + two follow-ups to handle slow file writes
      fetchList(true);
      const t1 = setTimeout(() => fetchList(true), 1500);
      const t2 = setTimeout(() => fetchList(true), 4000);
      return () => { clearTimeout(t1); clearTimeout(t2); };
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  // Safety net: if status is 'completed' but no files are visible yet (e.g. the
  // initial silent fetch ran before files were written, or loadingList timed out),
  // trigger one non-silent retry so the spinner shows and files load correctly.
  const retriedRef = useRef<string>('');
  useEffect(() => {
    const key = `${project?.id}-${phase.id}`;
    if (
      !loadingList &&
      filteredFiles.length === 0 &&
      status === 'completed' &&
      !error &&
      retriedRef.current !== key
    ) {
      retriedRef.current = key;
      fetchList(false, phase.id);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadingList, filteredFiles.length, status, phase.id, project?.id]);

  // Background prefetch all viewable documents after file list loads
  // This makes "Preview" feel instant — no spinner on click
  useEffect(() => {
    if (!project || filteredFiles.length === 0) return;
    let cancelled = false;
    const prefetch = async () => {
      const viewable = filteredFiles.filter(f => VIEWABLE.has(getExt(f.name)));
      for (const file of viewable) {
        if (cancelled) return;
        if (contents[file.name] !== undefined) continue; // already cached
        try {
          const text = await api.getDocumentText(project.id, file.name);
          if (!cancelled) setContents(prev => ({ ...prev, [file.name]: text }));
        } catch { /* silent — user can still click to retry */ }
        // Stagger requests to avoid hammering the backend
        await new Promise(r => setTimeout(r, 80));
      }
    };
    prefetch();
    return () => { cancelled = true; };
  // Only re-run when the file list changes — not on every contents update
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project, filteredFiles.map(f => f.name).join(',')]);

  const fetchContent = async (file: DocFile) => {
    if (!project) return;
    const ext = getExt(file.name);

    if (!VIEWABLE.has(ext)) {
      triggerDownload(file);
      return;
    }
    if (contents[file.name] !== undefined) {
      setExpanded(expanded === file.name ? null : file.name);
      return;
    }
    setLoadingFile(prev => ({ ...prev, [file.name]: true }));
    try {
      const text = await api.getDocumentText(project.id, file.name);
      setContents(prev => ({ ...prev, [file.name]: text }));
      setExpanded(file.name);
    } catch {
      setContents(prev => ({ ...prev, [file.name]: 'Could not load document.' }));
      setExpanded(file.name);
    }
    setLoadingFile(prev => ({ ...prev, [file.name]: false }));
  };

  const triggerDownload = (file: DocFile) => {
    if (!project) return;
    const a = document.createElement('a');
    a.href = `/api/v1/projects/${project.id}/documents/${encodeURIComponent(file.name)}`;
    a.download = file.name;
    a.click();
  };

  const triggerDocxDownload = async (file: DocFile) => {
    if (!project || docxConverting[file.name]) return;
    setDocxConverting(prev => ({ ...prev, [file.name]: true }));
    try {
      const resp = await fetch(`/api/v1/projects/${project.id}/docx/${file.name}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = file.name.replace(/\.md$/i, '.docx');
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    } catch (err) {
      console.error('DOCX download failed:', err);
    } finally {
      setDocxConverting(prev => ({ ...prev, [file.name]: false }));
    }
  };

  // ── Render states ─────────────────────────────────────────────────────────

  if (loadingList) {
    return (
      <div style={{ paddingTop: 24, display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text3)', fontSize: 13 }}>
        <div style={{ width: 14, height: 14, borderRadius: '50%', border: `2px solid ${phase.color}`, borderTopColor: 'transparent', animation: 'spin 0.8s linear infinite' }} />
        Loading documents...
      </div>
    );
  }

  if (error) {
    return (
      <div style={{
        marginTop: 24, padding: '16px 18px',
        background: 'rgba(220,38,38,0.07)', border: '1px solid rgba(220,38,38,0.25)',
        borderRadius: 8, fontSize: 13, color: '#ef4444',
        display: 'flex', gap: 10, alignItems: 'flex-start',
      }}>
        <span style={{ fontSize: 16, flexShrink: 0 }}>⚠</span>
        <div>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>Backend error</div>
          <div style={{ fontSize: 12, color: '#fca5a5' }}>{error}</div>
        </div>
      </div>
    );
  }

  if (filteredFiles.length === 0) {
    return (
      <div style={{ paddingTop: 24 }}>
        <div style={{
          padding: '28px', background: 'var(--panel)',
          border: `1px dashed ${phase.color}30`, borderRadius: 10,
          textAlign: 'center', marginBottom: 20,
        }}>
          {status === 'in_progress' ? (
            <GeneratingState phase={phase} />
          ) : status === 'pending' ? (
            <>
              <div style={{ fontSize: 28, marginBottom: 10, opacity: 0.25 }}>📁</div>
              <div style={{ fontSize: 14, color: 'var(--text2)', marginBottom: 6, fontWeight: 600 }}>
                {phase.id === 'P1' ? 'Start with a design chat' : `${phase.code} will generate documents automatically`}
              </div>
              <div style={{ fontSize: 12, color: 'var(--text4)', maxWidth: 360, margin: '0 auto', lineHeight: 1.65 }}>
                {phase.id === 'P1'
                  ? 'Use the ⚡ Chat tab to describe your hardware design. Once complete, the full pipeline runs automatically.'
                  : phase.manual
                  ? `This phase is completed manually in ${phase.externalTool || 'an external EDA tool'}.`
                  : 'The pipeline will run this phase automatically after previous phases complete.'
                }
              </div>
            </>
          ) : status === 'completed' ? (
            <>
              <div style={{ fontSize: 28, marginBottom: 10, opacity: 0.25 }}>📭</div>
              <div style={{ fontSize: 14, color: 'var(--text2)', marginBottom: 6 }}>Phase completed — no documents found</div>
              <div style={{ fontSize: 12, color: 'var(--text4)' }}>
                Output files will appear here automatically once the phase completes.
              </div>
            </>
          ) : (
            <div style={{ fontSize: 13, color: 'var(--text3)' }}>No documents for {phase.code} yet.</div>
          )}
        </div>

        {/* Phase Details — always show inputs/outputs/tools/metrics so user knows what's coming */}
        <PhaseDetails phase={phase} color={phase.color} />
      </div>
    );
  }

  return (
    <div style={{ paddingTop: 18 }}>
      {/* Phase details accordion — collapsed by default when documents exist */}
      <PhaseDetails phase={phase} color={phase.color} collapsed />

      {/* Markdown style injection */}
      <style>{`
        .md-body { color: var(--text2); font-size: 13.5px; }
        .md-body h1 { font-size: 21px; font-weight: 800; color: var(--text); font-family: 'Syne', sans-serif; margin: 24px 0 10px; border-bottom: 1px solid var(--border2); padding-bottom: 8px; }
        .md-body h2 { font-size: 17px; font-weight: 700; color: var(--text); font-family: 'Syne', sans-serif; margin: 20px 0 8px; }
        .md-body h3 { font-size: 14px; font-weight: 700; color: var(--text2); margin: 16px 0 6px; }
        .md-body h4 { font-size: 13px; font-weight: 600; color: var(--text3); margin: 12px 0 5px; }
        .md-body p  { margin: 8px 0; line-height: 1.8; }
        .md-body ul, .md-body ol { margin: 8px 0 8px 20px; padding: 0; }
        .md-body li { margin: 5px 0; line-height: 1.7; }
        .md-body strong { color: var(--text); }
        .md-body em { color: var(--text3); }
        .md-body code { font-family: 'JetBrains Mono', monospace; font-size: 11.5px; background: var(--panel2); color: var(--teal); padding: 1px 6px; border-radius: 3px; }
        .md-body pre { background: var(--panel2); border: 1px solid var(--border2); border-radius: 6px; padding: 14px 18px; overflow-x: auto; margin: 14px 0; }
        .md-body pre code { background: none; color: var(--text2); padding: 0; font-size: 12px; }
        .md-body blockquote { border-left: 3px solid var(--teal); margin: 12px 0; padding: 8px 16px; background: rgba(0,198,167,0.05); color: var(--text3); border-radius: 0 5px 5px 0; }
        .md-body table { width: 100%; border-collapse: collapse; margin: 14px 0; font-size: 12.5px; }
        .md-body th { background: var(--panel2); color: var(--text); padding: 9px 13px; text-align: left; border: 1px solid var(--border2); font-weight: 600; font-size: 11.5px; letter-spacing: 0.04em; }
        .md-body td { padding: 8px 13px; border: 1px solid var(--border2); color: var(--text2); vertical-align: top; line-height: 1.55; }
        .md-body tr:nth-child(even) td { background: rgba(0,0,0,0.03); }
        .md-body hr { border: none; border-top: 1px solid var(--border2); margin: 18px 0; }
        .md-body a { color: var(--blue); text-decoration: underline; }
        @keyframes shimmer { from { transform: translateX(-100%); } to { transform: translateX(200%); } }
      `}</style>

      {/* Stale-status banner: phase is PENDING but previous outputs exist.
          Skip P1 — docs exist there because the user just chatted (awaiting approval), not a stale run. */}
      {status === 'pending' && filteredFiles.length > 0 && phase.id !== 'P1' && (
        <div style={{
          marginBottom: 14,
          padding: '9px 14px',
          background: 'rgba(245,158,11,0.07)',
          border: '1px solid rgba(245,158,11,0.28)',
          borderRadius: 7,
          display: 'flex', alignItems: 'center', gap: 9,
        }}>
          <span style={{ fontSize: 14, flexShrink: 0 }}>⚠</span>
          <div>
            <span style={{ fontSize: 11.5, color: '#f59e0b', fontFamily: "'DM Mono',monospace", fontWeight: 600 }}>
              Previous run output
            </span>
            <span style={{ fontSize: 11.5, color: 'var(--text4)', marginLeft: 6 }}>
              These documents are from a prior pipeline run. Status shows PENDING — re-run this phase to refresh.
            </span>
          </div>
        </div>
      )}

      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{
            fontSize: 10, color: 'var(--text4)', fontFamily: "'DM Mono', monospace",
            letterSpacing: '0.1em',
          }}>
            {filteredFiles.length} {filteredFiles.length === 1 ? 'DOCUMENT' : 'DOCUMENTS'}
          </div>
          {status === 'in_progress' && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <div style={{ width: 7, height: 7, borderRadius: '50%', background: phase.color, animation: 'pulse 1.5s ease infinite' }} />
              <span style={{ fontSize: 10, color: phase.color, fontFamily: "'DM Mono', monospace" }}>UPDATING</span>
            </div>
          )}
        </div>
        <div style={{ display: 'flex', gap: 7, alignItems: 'center' }}>
          {/* Download all as ZIP */}
          {project && filteredFiles.length > 0 && (
            <a
              href={api.exportZipUrl(project.id)}
              download
              style={{
                fontSize: 11, color: '#22c55e',
                background: 'rgba(34,197,94,0.07)',
                border: '1px solid rgba(34,197,94,0.3)',
                borderRadius: 5, cursor: 'pointer',
                fontFamily: "'DM Mono', monospace",
                padding: '4px 11px', transition: 'all 0.15s',
                display: 'flex', alignItems: 'center', gap: 5,
                textDecoration: 'none', whiteSpace: 'nowrap',
              }}
              onMouseEnter={e => { (e.currentTarget as HTMLAnchorElement).style.background = 'rgba(34,197,94,0.14)'; (e.currentTarget as HTMLAnchorElement).style.boxShadow = '0 0 10px rgba(34,197,94,0.2)'; }}
              onMouseLeave={e => { (e.currentTarget as HTMLAnchorElement).style.background = 'rgba(34,197,94,0.07)'; (e.currentTarget as HTMLAnchorElement).style.boxShadow = 'none'; }}
            >
              ↓ Export ZIP
            </a>
          )}
        </div>
      </div>

      {/* File list */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {filteredFiles.map(file => {
          const ext = getExt(file.name);
          const color = extColor(ext);
          const isViewable = VIEWABLE.has(ext);
          const isOpen = expanded === file.name;
          const isLoading = loadingFile[file.name];
          const contentLoaded = contents[file.name] !== undefined;

          return (
            <div key={file.name} style={{
              border: `1px solid ${isOpen ? phase.color + '60' : 'var(--border2)'}`,
              borderRadius: 10, overflow: 'hidden',
              transition: 'border-color 0.2s',
              background: isOpen ? 'var(--panel2)' : 'var(--panel)',
            }}>
              {/* File row */}
              <div style={{
                display: 'flex', alignItems: 'center', gap: 12, padding: '13px 16px',
                background: isOpen ? `${phase.color}06` : 'transparent',
              }}>
                {/* File icon */}
                <FileIcon ext={ext} color={color} />

                {/* File info */}
                <div
                  onClick={() => fetchContent(file)}
                  style={{ flex: 1, minWidth: 0, cursor: 'pointer' }}
                >
                  <div style={{
                    fontSize: 13.5, color: 'var(--text)', fontWeight: 600,
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    marginBottom: 2,
                  }}>
                    {file.name}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{
                      fontSize: 10, padding: '1px 7px', borderRadius: 3,
                      background: `${color}12`, color, border: `1px solid ${color}22`,
                      fontFamily: "'DM Mono', monospace",
                    }}>
                      {extLabel(ext)}
                    </span>
                    <span style={{ fontSize: 11, color: 'var(--text4)' }}>
                      {formatSize(file.size)}
                    </span>
                  </div>
                </div>

                {/* Loading spinner */}
                {isLoading && (
                  <div style={{ width: 14, height: 14, borderRadius: '50%', border: `2px solid ${phase.color}`, borderTopColor: 'transparent', animation: 'spin 0.8s linear infinite', flexShrink: 0 }} />
                )}

                {/* Action buttons */}
                <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                  {isViewable && (
                    <button
                      onClick={() => fetchContent(file)}
                      style={{
                        fontSize: 12, color: isOpen ? phase.color : 'var(--text3)',
                        background: isOpen ? `${phase.color}12` : 'var(--panel2)',
                        border: `1px solid ${isOpen ? phase.color + '44' : 'var(--panel3)'}`,
                        borderRadius: 6, cursor: 'pointer',
                        fontFamily: "'DM Mono', monospace",
                        padding: '5px 12px', transition: 'all 0.15s',
                        whiteSpace: 'nowrap',
                      }}
                      onMouseEnter={e => { if (!isOpen) { e.currentTarget.style.color = phase.color; e.currentTarget.style.borderColor = `${phase.color}44`; }}}
                      onMouseLeave={e => { if (!isOpen) { e.currentTarget.style.color = 'var(--text3)'; e.currentTarget.style.borderColor = 'var(--panel3)'; }}}
                    >
                      {isOpen ? '▲ Close' : '▼ Preview'}
                    </button>
                  )}

                  {/* ↓ DOCX button — only for .md files */}
                  {getExt(file.name) === 'md' && (() => {
                    const isConverting = !!docxConverting[file.name];
                    return (
                      <button
                        onClick={(e) => { e.stopPropagation(); triggerDocxDownload(file); }}
                        disabled={isConverting}
                        title={isConverting ? 'Converting to Word document…' : `Convert ${file.name} to Word document (.docx)`}
                        style={{
                          fontSize: 12,
                          color: isConverting ? '#3b82f6' : 'var(--text3)',
                          background: isConverting ? 'rgba(59,130,246,0.08)' : 'var(--panel2)',
                          border: `1px solid ${isConverting ? '#3b82f666' : 'var(--panel3)'}`,
                          borderRadius: 6,
                          cursor: isConverting ? 'not-allowed' : 'pointer',
                          fontFamily: "'DM Mono', monospace",
                          padding: '5px 12px', transition: 'all 0.15s',
                          display: 'flex', alignItems: 'center', gap: 6,
                          whiteSpace: 'nowrap', opacity: isConverting ? 0.85 : 1,
                        }}
                        onMouseEnter={e => { if (!isConverting) { e.currentTarget.style.color = '#3b82f6'; e.currentTarget.style.borderColor = '#3b82f666'; e.currentTarget.style.background = 'rgba(59,130,246,0.08)'; }}}
                        onMouseLeave={e => { if (!isConverting) { e.currentTarget.style.color = 'var(--text3)'; e.currentTarget.style.borderColor = 'var(--panel3)'; e.currentTarget.style.background = 'var(--panel2)'; }}}
                      >
                        {isConverting ? (
                          <>
                            <span style={{ width: 10, height: 10, borderRadius: '50%', border: '2px solid #3b82f6', borderTopColor: 'transparent', display: 'inline-block', animation: 'spin 0.7s linear infinite', flexShrink: 0 }} />
                            Converting…
                          </>
                        ) : '↓ DOCX'}
                      </button>
                    );
                  })()}

                  <button
                    onClick={(e) => { e.stopPropagation(); triggerDownload(file); }}
                    title={`Download ${file.name}`}
                    style={{
                      fontSize: 12, color: 'var(--text3)',
                      background: 'var(--panel2)',
                      border: '1px solid var(--panel3)',
                      borderRadius: 6, cursor: 'pointer',
                      fontFamily: "'DM Mono', monospace",
                      padding: '5px 12px', transition: 'all 0.15s',
                      display: 'flex', alignItems: 'center', gap: 5,
                      whiteSpace: 'nowrap',
                    }}
                    onMouseEnter={e => { e.currentTarget.style.color = '#22c55e'; e.currentTarget.style.borderColor = '#22c55e66'; e.currentTarget.style.background = 'rgba(34,197,94,0.08)'; }}
                    onMouseLeave={e => { e.currentTarget.style.color = 'var(--text3)'; e.currentTarget.style.borderColor = 'var(--panel3)'; e.currentTarget.style.background = 'var(--panel2)'; }}
                  >
                    ↓ Download
                  </button>
                </div>
              </div>

              {/* Content pane */}
              {isOpen && contentLoaded && (
                <div style={{
                  borderTop: `1px solid ${phase.color}25`,
                  background: 'var(--panel)',
                  maxHeight: 720,
                  overflowY: 'auto',
                }}>
                  {ext === 'md' || ext === 'txt' ? (
                    <MarkdownRenderer content={contents[file.name]} color={phase.color} />
                  ) : ext === 'json' ? (
                    /* JSON: pretty-print with syntax-tinted scrollable pane */
                    <div>
                      <div style={{ padding: '8px 22px 4px', background: 'rgba(245,158,11,0.06)', borderBottom: '1px solid rgba(245,158,11,0.15)', display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ fontSize: 10, color: '#f59e0b', fontFamily: "'DM Mono', monospace", letterSpacing: 1 }}>JSON</span>
                        {file.name.includes('sbom') && (
                          <span style={{ fontSize: 10, color: '#10b981', fontFamily: "'DM Mono', monospace", background: 'rgba(16,185,129,0.1)', padding: '2px 7px', borderRadius: 3, border: '1px solid rgba(16,185,129,0.3)' }}>CycloneDX SBOM</span>
                        )}
                      </div>
                      <pre style={{ margin: 0, padding: '14px 22px', fontSize: 11, color: '#f59e0b', lineHeight: 1.7, whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontFamily: "'JetBrains Mono', monospace" }}>
                        {(() => { try { return JSON.stringify(JSON.parse(contents[file.name]), null, 2); } catch { return contents[file.name]; } })()}
                      </pre>
                    </div>
                  ) : ext === 'py' || ext === 'c' || ext === 'cpp' || ext === 'h' ? (
                    /* Code files: language-labelled monospace block */
                    <div>
                      <div style={{ padding: '8px 22px 4px', background: `${extColor(ext)}0d`, borderBottom: `1px solid ${extColor(ext)}25`, display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ fontSize: 10, color: extColor(ext), fontFamily: "'DM Mono', monospace", letterSpacing: 1 }}>{extLabel(ext).toUpperCase()}</span>
                        {file.name === 'gui_application.py' && (
                          <span style={{ fontSize: 10, color: '#8b5cf6', fontFamily: "'DM Mono', monospace", background: 'rgba(139,92,246,0.1)', padding: '2px 7px', borderRadius: 3, border: '1px solid rgba(139,92,246,0.3)' }}>PySide6 Qt GUI • pip install PySide6 pyserial && python {file.name}</span>
                        )}
                      </div>
                      <pre style={{ margin: 0, padding: '14px 22px', fontSize: 11, color: 'var(--text2)', lineHeight: 1.7, whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontFamily: "'JetBrains Mono', monospace" }}>
                        {contents[file.name]}
                      </pre>
                    </div>
                  ) : (
                    <pre style={{
                      margin: 0, padding: '18px 22px',
                      fontSize: 12, color: 'var(--text2)', lineHeight: 1.8,
                      whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                      fontFamily: "'JetBrains Mono', monospace",
                    }}>
                      {contents[file.name]}
                    </pre>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
