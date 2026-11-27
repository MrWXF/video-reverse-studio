export type JobStatus = "uploaded" | "queued" | "running" | "done" | "failed" | "cancelled";

export type MetricValue = number | string | boolean | null | string[];

export interface Job {
  id: string;
  status: JobStatus;
  step: string;
  progress: number;
  error: string;
  metrics: Record<string, MetricValue>;
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
  metrics: Record<string, MetricValue>;
  cost: UsageCost;
}

export interface HealthStatus {
  status: string;
  llm_provider: string;
  llm_enabled: boolean;
  analysis_mode: "mock" | "live" | "degraded";
  auth_enabled: boolean;
  insecure_no_auth: boolean;
  database: string;
  ffmpeg: boolean;
  ffprobe: boolean;
  max_upload_mb: number;
  active_jobs: number;
  active_jobs_by_kind: Record<string, number>;
  queue: Record<string, number>;
}

export interface PromptShot {
  index: number;
  start_s: number;
  end_s: number;
  duration: number;
  shot_type: string;
  camera_movement: string;
  subject: string;
  action: string;
  scene: string;
  lighting: string;
  color_palette: string[];
  prompt: string;
  negative_prompt: string;
  transition: string;
  remake_notes: string;
  source_shot_index: number | null;
  locked_fields: string[];
}

export interface PromptPlan {
  title: string;
  summary: string;
  target_model: string;
  language: string;
  duration_s: number;
  aspect_ratio: string;
  global_style: string;
  shots: PromptShot[];
  assumptions: string[];
  warnings: string[];
}

export interface PromptBrief {
  title: string;
  idea: string;
  target_model: string;
  language: "en" | "zh";
  duration_s: number;
  aspect_ratio: string;
  shot_count: number;
  style: string;
  mood: string;
  audience: string;
  negative_prompt: string;
  constraints: string[];
  reference_project_id: string | null;
  reference_mode: "style" | "structure" | "full";
}

export interface PromptProject {
  id: string;
  title: string;
  status: JobStatus;
  step: string;
  progress: number;
  error: string;
  metrics: Record<string, MetricValue>;
  target_model: string;
  shot_count: number;
  brief: Partial<PromptBrief>;
  version_count: number;
  source_project_id: string | null;
  reference_mode: string;
  export_url: string;
  created_at: string | null;
  updated_at: string | null;
  plan?: PromptPlan;
}

export interface GenerationShotResult {
  shot_index: number;
  status: string;
  download_url: string;
  media_type: string;
  error: string;
  warnings: string[];
}

export interface GenerationJob {
  id: string;
  prompt_project_id: string;
  provider: string;
  model: string;
  status: string;
  step: string;
  progress: number;
  error: string;
  shot_indices: number[];
  result: { provider: string; shots: GenerationShotResult[] };
  created_at: string | null;
  updated_at: string | null;
}
