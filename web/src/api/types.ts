export type JobStatus = "uploaded" | "queued" | "running" | "done" | "failed" | "cancelled";

export interface Job {
  id: string;
  status: JobStatus;
  step: string;
  progress: number;
  error: string;
  metrics: Record<string, number | string | boolean | null>;
  updated_at: string | null;
}

export interface ShotAnalysis {
  shot_type?: string;
  camera_movement?: string;
  subject?: string;
  scene?: string;
  visual_style?: string;
  lighting?: string;
  color_palette?: string[];
  origin?: string;
  confidence?: number;
  evidence?: string[];
  prompt?: string;
  remake_notes?: string;
}

export interface Shot {
  id: number;
  index: number;
  start_s: number;
  end_s: number;
  keyframe_url: string;
  transcript: string;
  origin: string;
  confidence: number;
  analysis: ShotAnalysis;
}

export interface ProjectSummary {
  id: string;
  title: string;
  status: JobStatus;
  duration: number | null;
  width: number | null;
  height: number | null;
  fps: number | null;
  timeline_min_shot_seconds: number | null;
  shot_count: number;
  created_at: string | null;
  video_url: string;
  recipe_url: string;
  job: Job | null;
}

export interface PromptProjectLink {
  id: string;
  title: string;
  status: JobStatus;
  reference_mode: string;
}

export interface ProjectDetail extends ProjectSummary {
  shots: Shot[];
  prompt_projects: PromptProjectLink[];
}

export interface TimelineMutation {
  job_id: string;
  status: "queued";
  action: "boundary" | "split" | "merge" | "reanalyze";
  affected_shot_ids: number[];
  prompt_projects_invalidated: number;
}

export interface QualityField {
  field: string;
  label: string;
  count: number;
  affected_shots: number;
  rate: number | null;
}

export interface QualityTrendPoint {
  date: string;
  edit_events: number;
  field_corrections: number;
  origin_corrections: number;
  edited_shots: number;
}

export interface QualityProject {
  id: string;
  title: string;
  status: JobStatus;
  shot_count: number;
  edit_events: number;
  edited_shots: number;
  origin_corrections: number;
  last_edit_at: string | null;
}

export interface QualitySummary {
  projects: number;
  shots: number;
  edit_events: number;
  edited_shots: number;
  origin_corrections: number;
  origin_accuracy: number | null;
  correction_rate: number | null;
  analysis_runs: number;
  average_processing_seconds: number | null;
  total_tokens: number;
  total_calls: number;
}

export interface QualityDashboard {
  generated_at: string;
  window: {
    days: number;
    start_date: string;
    end_date: string;
  };
  summary: QualitySummary;
  fields: QualityField[];
  trend: QualityTrendPoint[];
  projects: QualityProject[];
  suggestions: string[];
  note: string;
}

export interface CostEstimate {
  estimated_shots: number;
  shot_count_source: "manual" | "duration";
  cost: {
    calls?: number;
    prompt_tokens?: number;
    completion_tokens?: number;
    estimated_cost?: number | null;
    currency?: string;
    priced?: boolean;
    note?: string;
  };
  suggestions: string[];
}

export interface UsageCost {
  calls?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  estimated_cost?: number | null;
  currency?: string;
  priced?: boolean;
  note?: string;
}

export interface ProjectCost {
  project_id: string;
  metrics: Record<string, number | string | boolean | null>;
  cost: UsageCost;
}
