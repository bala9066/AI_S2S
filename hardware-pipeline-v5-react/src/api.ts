import { Project, Statuses, StatusesRaw } from './types';

// Same-origin when served by FastAPI (port 8000 or behind a proxy).
// Fall back to explicit localhost:8000 when opened directly as file:// or via Vite dev server.
const BASE = (
  window.location.protocol === 'file:' ||
  (window.location.port !== '8000' && window.location.port !== '')
)
  ? 'http://localhost:8000'
  : '';

async function req<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) {
    let detail = '';
    try { const j = await res.json(); detail = j.detail || ''; } catch { /* ignore */ }
    throw new Error(`HTTP ${res.status}: ${res.statusText}${detail ? ' — ' + detail : ''} [${path}]`);
  }
  return res.json();
}

export interface ChatResult {
  text: string;
  phaseComplete: boolean;
  draftPending: boolean;
}

export const api = {
  listProjects: () => req<Project[]>('/api/v1/projects'),

  createProject: (data: { name: string; description: string; design_type: string }) =>
    req<Project>('/api/v1/projects', { method: 'POST', body: JSON.stringify(data) }),

  getProject: (id: number) => req<Project>(`/api/v1/projects/${id}`),

  getStatus: async (id: number): Promise<Statuses> => {
    const r = await req<{ phase_statuses: Record<string, unknown> }>(`/api/v1/projects/${id}/status`);
    const raw = r.phase_statuses || {};
    // Backend stores phase_statuses as {"P1": {"status": "completed", "updated_at": "..."}, ...}
    // Flatten to {"P1": "completed", ...} for the UI
    const flat: Statuses = {};
    for (const [key, val] of Object.entries(raw)) {
      if (typeof val === 'string') {
        flat[key] = val as Statuses[string];
      } else if (val && typeof val === 'object' && 'status' in val) {
        flat[key] = (val as { status: string }).status as Statuses[string];
      } else {
        flat[key] = 'pending';
      }
    }
    return flat;
  },

  getStatusRaw: async (id: number): Promise<StatusesRaw> => {
    const r = await req<{ phase_statuses: Record<string, unknown> }>(`/api/v1/projects/${id}/status`);
    const raw = r.phase_statuses || {};
    const result: StatusesRaw = {};
    for (const [key, val] of Object.entries(raw)) {
      if (typeof val === 'string') {
        result[key] = { status: val as StatusesRaw[string]['status'] };
      } else if (val && typeof val === 'object' && 'status' in val) {
        const entry = val as { status: string; updated_at?: string };
        result[key] = {
          status: entry.status as StatusesRaw[string]['status'],
          updated_at: entry.updated_at,
        };
      }
    }
    return result;
  },

  runPipeline: (id: number) =>
    req(`/api/v1/projects/${id}/pipeline/run`, { method: 'POST' }),

  executePhase: (id: number, phaseId: string) =>
    req(`/api/v1/projects/${id}/phases/${phaseId}/execute`, { method: 'POST' }),

  // Reset stale phases to 'pending' then re-run the pipeline
  resetAndRerun: (id: number, phaseIds: string[]) =>
    req(`/api/v1/projects/${id}/phases/reset`, {
      method: 'POST',
      body: JSON.stringify({ phase_ids: phaseIds }),
    }),

  // Export all project documents as a ZIP — returns a download URL
  exportZipUrl: (id: number) => `${BASE}/api/v1/projects/${id}/export`,

  chat: async (id: number, message: string): Promise<ChatResult> => {
    const result = await req<{
      response?: string; message?: string; content?: string;
      phase_complete?: boolean;
    }>(
      `/api/v1/projects/${id}/chat`,
      { method: 'POST', body: JSON.stringify({ message }) }
    );
    // Use `result.response` if it is defined (even if it's an empty string).
    // Only fall through to other fields or JSON.stringify when the key is truly absent.
    const text = (result.response != null)
      ? result.response
      : (result.message != null)
        ? result.message
        : (result.content != null)
          ? result.content
          : JSON.stringify(result);
    return { text, phaseComplete: !!result.phase_complete, draftPending: !!result.draft_pending };
  },

  listDocuments: (id: number): Promise<{ name: string; size: number }[]> =>
    req(`/api/v1/projects/${id}/documents`),

  getDocumentText: async (id: number, filename: string): Promise<string> => {
    const res = await fetch(`${BASE}/api/v1/projects/${id}/documents/${encodeURIComponent(filename)}`);
    if (!res.ok) throw new Error(`${res.status}`);
    return res.text();
  },

  getConversationHistory: async (id: number): Promise<{ role: string; content: string }[]> => {
    const proj = await req<{ conversation_history?: { role: string; content: string }[] }>(
      `/api/v1/projects/${id}`
    );
    return (proj.conversation_history || []).filter(
      m => (m.role === 'user' || m.role === 'assistant') && m.content
    );
  },

  /** Call POST /clarify — returns structured card data (tool_use forced, zero parse failures). */
  clarifyRequirement: async (
    id: number,
    requirement: string,
    designType: string = 'RF'
  ): Promise<{
    intro: string;
    questions: Array<{ id: string; question: string; why: string; options: string[] }>;
  }> => {
    const res = await fetch(`${BASE}/api/v1/projects/${id}/clarify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ requirement, design_type: designType }),
    });
    if (!res.ok) throw new Error(`Clarify failed: ${res.status}`);
    return res.json();
  },
};
