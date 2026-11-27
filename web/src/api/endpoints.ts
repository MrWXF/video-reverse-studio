import { api } from "./client";
import type {
  CostEstimate,
  GenerationJob,
  HealthStatus,
  ProjectCost,
  ProjectDetail,
  ProjectSummary,
  PromptBrief,
  PromptProject,
  QualityDashboard,
  TimelineMutation,
} from "./types";

export function fetchHealth(signal?: AbortSignal): Promise<HealthStatus> {
  return api<HealthStatus>("/healthz", { signal });
}

export function fetchQuality(days = 30, signal?: AbortSignal): Promise<QualityDashboard> {
  return api<QualityDashboard>(`/api/insights/quality?days=${days}`, { signal });
}

export function fetchProjects(signal?: AbortSignal): Promise<ProjectSummary[]> {
  return api<ProjectSummary[]>("/api/projects", { signal });
}

export function fetchProject(projectId: string, signal?: AbortSignal): Promise<ProjectDetail> {
  return api<ProjectDetail>(`/api/projects/${encodeURIComponent(projectId)}`, { signal });
}

export function estimateCost(videoDuration: number, signal?: AbortSignal): Promise<CostEstimate> {
  return api<CostEstimate>("/api/projects/estimate-cost", {
    method: "POST",
    body: JSON.stringify({ video_duration: videoDuration }),
    signal,
  });
}

export function createProject(form: FormData): Promise<{ project_id: string; job_id: string; status: string }> {
  return api("/api/projects", { method: "POST", body: form });
}

export function fetchProjectCost(projectId: string, signal?: AbortSignal): Promise<ProjectCost> {
  return api<ProjectCost>(`/api/projects/${encodeURIComponent(projectId)}/cost`, { signal });
}

export function cancelProject(projectId: string): Promise<unknown> {
  return api(`/api/projects/${encodeURIComponent(projectId)}/cancel`, { method: "POST" });
}

export function reanalyzeProject(projectId: string): Promise<unknown> {
  return api(`/api/projects/${encodeURIComponent(projectId)}/analyze`, { method: "POST" });
}

export function deleteProject(projectId: string): Promise<unknown> {
  return api(`/api/projects/${encodeURIComponent(projectId)}`, { method: "DELETE" });
}

export function updateTimelineBoundary(
  projectId: string,
  shotId: number,
  boundarySeconds: number,
): Promise<TimelineMutation> {
  return api<TimelineMutation>(
    `/api/projects/${encodeURIComponent(projectId)}/shots/${encodeURIComponent(shotId)}/boundary`,
    {
      method: "PATCH",
      body: JSON.stringify({ boundary_s: boundarySeconds }),
    },
  );
}

export function splitTimelineShot(
  projectId: string,
  shotId: number,
  splitAt: number,
): Promise<TimelineMutation> {
  return api<TimelineMutation>(
    `/api/projects/${encodeURIComponent(projectId)}/shots/${encodeURIComponent(shotId)}/split`,
    {
      method: "POST",
      body: JSON.stringify({ split_at: splitAt }),
    },
  );
}

export function mergeTimelineShots(
  projectId: string,
  shotIds: [number, number],
): Promise<TimelineMutation> {
  return api<TimelineMutation>(`/api/projects/${encodeURIComponent(projectId)}/shots/merge`, {
    method: "POST",
    body: JSON.stringify({ shot_ids: shotIds }),
  });
}

export function reanalyzeTimelineShot(
  projectId: string,
  shotId: number,
): Promise<TimelineMutation> {
  return api<TimelineMutation>(
    `/api/projects/${encodeURIComponent(projectId)}/shots/${encodeURIComponent(shotId)}/reanalyze`,
    { method: "POST" },
  );
}

export function fetchPromptProjects(signal?: AbortSignal): Promise<PromptProject[]> {
  return api<PromptProject[]>("/api/prompt-projects", { signal });
}

export function fetchPromptProject(projectId: string, signal?: AbortSignal): Promise<PromptProject> {
  return api<PromptProject>(`/api/prompt-projects/${encodeURIComponent(projectId)}`, { signal });
}

export function createPromptProject(brief: PromptBrief): Promise<{ prompt_project_id: string; status: string }> {
  return api("/api/prompt-projects", {
    method: "POST",
    body: JSON.stringify(brief),
  });
}

export function regeneratePromptProject(projectId: string): Promise<unknown> {
  return api(`/api/prompt-projects/${encodeURIComponent(projectId)}/regenerate`, { method: "POST" });
}

export function fetchGenerationJobs(projectId: string, signal?: AbortSignal): Promise<GenerationJob[]> {
  return api<GenerationJob[]>(
    `/api/prompt-projects/${encodeURIComponent(projectId)}/generation-jobs`,
    { signal },
  );
}

export function startGeneration(
  projectId: string,
  payload: { shot_indices?: number[]; aspect_ratio?: string; model?: string } = {},
): Promise<GenerationJob> {
  return api<GenerationJob>(
    `/api/prompt-projects/${encodeURIComponent(projectId)}/generation-jobs`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}
