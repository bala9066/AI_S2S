/**
 * Shared Mermaid loader — single source of truth.
 *
 * Both ChatView and DocumentsView must import from here so that:
 *  1. The CDN <script> is appended exactly ONCE.
 *  2. mermaid.initialize() is called exactly ONCE with the correct config.
 *  3. suppressErrorRendering + logLevel are always in effect.
 */

declare global {
  interface Window {
    mermaid?: {
      initialize: (cfg: object) => void;
      render: (id: string, code: string) => Promise<{ svg: string }>;
      parse: (code: string) => Promise<unknown>;
    };
  }
}

const MERMAID_CDN = 'https://cdn.jsdelivr.net/npm/mermaid@10.6.1/dist/mermaid.min.js';

const MERMAID_CONFIG = {
  startOnLoad: false,
  securityLevel: 'loose' as const,
  theme: 'dark' as const,
  // 5 = fatal only — kills internal console noise and OS-level toast notifications
  logLevel: 5,
  // Prevent Mermaid from appending its own red error div to document.body
  suppressErrorRendering: true,
  themeVariables: {
    primaryColor: '#1a2235',
    primaryTextColor: '#e2e8f0',
    primaryBorderColor: '#00c6a7',
    lineColor: '#3b82f6',
    secondaryColor: '#0d1423',
    tertiaryColor: '#2a3a50',
    fontFamily: "'DM Mono', monospace",
    fontSize: '13px',
  },
};

type Callback = () => void;

let _state: 'idle' | 'loading' | 'ready' | 'failed' = 'idle';
let _promise: Promise<void> | null = null;
const _callbacks: Callback[] = [];

/** Remove any scratch DOM nodes Mermaid inserts into document.body */
export function purgeMermaidScratch(id: string): void {
  [`#${id}`, `#d${id}`, `#dmermaid`, `.mermaid-error`].forEach(sel => {
    try { document.querySelectorAll(sel).forEach(el => el.remove()); } catch { /* ignore */ }
  });
  // Also sweep any body-direct children that look like Mermaid error divs
  try {
    document.body.querySelectorAll('[id^="mermaid-"], [id^="dmermaid"], .mermaid').forEach(el => {
      // Only remove if it's a direct scratch node (no parent component wrapper)
      if (el.parentElement === document.body) el.remove();
    });
  } catch { /* ignore */ }
}

/** Returns a promise that resolves when window.mermaid is ready. */
export function loadMermaid(): Promise<void> {
  // Already ready
  if (_state === 'ready' && window.mermaid) return Promise.resolve();

  // Already loading — return same promise
  if (_promise) return _promise;

  // If window.mermaid was loaded externally (e.g. dev HMR), adopt it
  if (window.mermaid) {
    window.mermaid.initialize(MERMAID_CONFIG);
    _state = 'ready';
    return Promise.resolve();
  }

  _state = 'loading';
  _promise = new Promise<void>((resolve, reject) => {
    const script = document.createElement('script');
    script.src = MERMAID_CDN;
    script.onload = () => {
      if (window.mermaid) {
        window.mermaid.initialize(MERMAID_CONFIG);
        _state = 'ready';
        _callbacks.forEach(cb => cb());
        _callbacks.length = 0;
        resolve();
      } else {
        _state = 'failed';
        _promise = null;
        reject(new Error('Mermaid loaded but window.mermaid is undefined'));
      }
    };
    script.onerror = () => {
      _state = 'failed';
      _promise = null;
      reject(new Error('Failed to load Mermaid from CDN'));
    };
    document.head.appendChild(script);
  });

  return _promise;
}

/** Callback-style wrapper kept for ChatView compatibility */
export function ensureMermaid(cb: Callback): void {
  loadMermaid().then(cb).catch(cb); // still call cb so components can show fallback
}

let _idCounter = 0;
export function nextMermaidId(): string {
  return `mmd-${++_idCounter}`;
}
