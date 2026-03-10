import type { Project, Statuses } from './types';

const BASE = (window.location.port === '8000' || window.location.port === '') ? '' : 'http://localhost:8000';

async function req<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export const api = {
  listProjects: () => req<Project[]>('/api/v1/projects'),

  createProject: (data: { name: string; description: string; design_type: string }) =>
    req<Project>('/api/v1/projects', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getProject: (id: number) => req<Project>(`/api/v1/projects/${id}`),

  getStatus: async (id: number): Promise<Statuses> => {
    const result = await req<{ phase_statuses: Record<string, { status: string }> }>(`/api/v1/projects/${id}/status`);
    // Extract status from nested objects: { "P1": {"status": "pending"} } -> { "P1": "pending" }
    const statuses: Statuses = {};
    for (const [phaseId, data] of Object.entries(result.phase_statuses || {})) {
      statuses[phaseId] = (data as any).status as any;
    }
    return statuses;
  },

  runPipeline: (id: number) =>
    req(`/api/v1/projects/${id}/pipeline/run`, { method: 'POST' }),

  executePhase: (id: number, phaseId: string) =>
    req(`/api/v1/projects/${id}/phases/${phaseId}/execute`, { method: 'POST' }),

  chat: async (
    id: number,
    message: string,
    onToken: (text: string) => void
  ): Promise<void> => {
    const result = await req<{ response?: string; message?: string; content?: string }>(
      `/api/v1/projects/${id}/chat`,
      { method: 'POST', body: JSON.stringify({ message }) }
    );
    const text = result.response || result.message || result.content || JSON.stringify(result);
    onToken(text);
  },
};
