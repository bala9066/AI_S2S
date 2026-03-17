export type PhaseStatusValue = 'pending' | 'in_progress' | 'completed' | 'failed' | 'draft_pending';

export interface PhaseStatusEntry {
  status: PhaseStatusValue;
  updated_at?: string; // ISO string from backend
}

export type StatusesRaw = Record<string, PhaseStatusEntry>;

export interface Project {
  id: number;
  name: string;
  description?: string;
  design_type?: string;
  status?: string;
  output_dir?: string;
  created_at?: string;
  conversation_history?: unknown[];
}

export type Statuses = Record<string, PhaseStatusValue>;

export interface SubStep {
  label: string;
  time: string;
  detail: string;
}

export interface PhaseMeta {
  id: string;           // "P1", "P2", "P8a" etc
  code: string;         // "P01", "P02" etc
  num: number;
  name: string;
  tagline: string;
  color: string;
  auto: boolean;
  manual: boolean;
  time: string;
  subSteps: SubStep[];
  metrics: { timeSaved: string; errorReduction: string; confidence: string; costImpact: string };
  inputs: string[];
  outputs: string[];
  tools: string[];
  externalTool?: string;
}

export type CenterTab = 'chat' | 'documents';
export type AppMode = 'landing' | 'pipeline';
