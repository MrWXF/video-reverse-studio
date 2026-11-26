import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  cancelProject,
  deleteProject,
  fetchProject,
  fetchProjectCost,
  reanalyzeProject,
} from "../../api/endpoints";
import type { JobStatus, ProjectDetail as ProjectDetailData } from "../../api/types";
import { useApiQuery } from "../../hooks/useApiQuery";
import { useJobEvents } from "../../hooks/useJobEvents";
import { useUiStore } from "../../store/uiStore";
import { formatCost, formatNumber, STATUS_LABELS } from "../../utils/format";
import { ShotCard } from "./ShotCard";
import { TimelineEditor } from "./TimelineEditor";

const STEP_HINTS: Record<string, string> = {
  probing: "正在读取视频元数据",
  segmenting: "正在检测镜头切换",
  extracting: "正在抽取关键帧",
  transcribing: "正在转写音频",
  analyzing: "正在逐镜分析画面",
  fusing: "正在汇总分镜与节奏",
  done: "完成",
  failed: "任务失败",
  cancelled: "已取消",
};

function isRunning(status: JobStatus | undefined): boolean {
  return status === "queued" || status === "running";
}

function Summary({ project }: { project: ProjectDetailData }) {
  const shots = project.shots;
  const first = shots[0]?.analysis;
  const palette = shots.flatMap((shot) => shot.analysis.color_palette ?? []).filter(Boolean).slice(0, 5);
  const average = shots.length ? formatNumber((project.duration ?? 0) / shots.length, 1) : "—";
  return (
    <div className="summary-grid">
      <div className="summary-card">
        <span>VISUAL STYLE</span>
        <strong>{first?.visual_style || first?.shot_type || "等待画面分析"}</strong>
        <p>{[first?.subject, first?.scene].filter(Boolean).join(" · ") || "镜头信息将在分析完成后出现"}</p>
      </div>
      <div className="summary-card">
        <span>RHYTHM</span>
        <strong>{shots.length} 个镜头</strong>
        <p>平均每镜 {average}s · {formatNumber(project.fps, 1)} fps</p>
      </div>
      <div className="summary-card">
        <span>PALETTE</span>
        <strong>{palette.length} 色提取</strong>
        <div className="palette-inline" aria-label="主色板">
          {palette.map((color, index) => <i style={{ background: color }} key={`${color}-${index}`} />)}
        </div>
      </div>
    </div>
  );
}

function Usage({ projectId }: { projectId: string }) {
  const costQuery = useApiQuery((signal) => fetchProjectCost(projectId, signal), [projectId]);
  const data = costQuery.data;
  if (!data) {
    return null;
  }
  return (
    <div className="usage-strip is-compact">
      <div className="usage-metric"><span>CALLS</span><strong>{formatNumber(data.cost.calls, 0)}</strong></div>
      <div className="usage-metric"><span>INPUT</span><strong>{formatNumber(data.cost.prompt_tokens, 0)}</strong><small>tokens</small></div>
      <div className="usage-metric"><span>OUTPUT</span><strong>{formatNumber(data.cost.completion_tokens, 0)}</strong><small>tokens</small></div>
      <div className="usage-metric is-cost"><span>EST. COST</span><strong>{formatCost(data.cost)}</strong><small>{data.cost.note || "估算值"}</small></div>
    </div>
  );
}

export function ProjectDetail({ projectId, onChanged }: { projectId: string; onChanged: () => void }) {
  const navigate = useNavigate();
  const showToast = useUiStore((state) => state.showToast);
  const query = useApiQuery((signal) => fetchProject(projectId, signal), [projectId]);
  const videoRef = useRef<HTMLVideoElement>(null);
  const project = query.data;
  const running = isRunning(project?.status);
  const [recipeText, setRecipeText] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const previousStatus = useRef<JobStatus | null>(null);

  useJobEvents(project?.job?.id, running, query.refresh);

  useEffect(() => {
    if (!project) {
      return undefined;
    }
    const controller = new AbortController();
    if (project.status !== "done") {
      setRecipeText("");
      return () => controller.abort();
    }
    fetch(`${project.recipe_url}?t=${Date.now()}`, { credentials: "same-origin", signal: controller.signal })
      .then((response) => (response.ok ? response.text() : ""))
      .then((text) => setRecipeText(text))
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setRecipeText("");
        }
      });
    return () => controller.abort();
  }, [project?.job?.id, project?.recipe_url, project?.status]);

  useEffect(() => {
    if (!project) {
      return;
    }
    if (previousStatus.current !== null && previousStatus.current !== project.status) {
      onChanged();
    }
    previousStatus.current = project.status;
  }, [onChanged, project]);

  const run = async (label: string, operation: () => Promise<unknown>, success: string) => {
    setBusy(label);
    try {
      await operation();
      showToast(success, "success");
      query.refresh();
      onChanged();
      return true;
    } catch (error) {
      showToast(error instanceof Error ? error.message : "操作失败", "error");
      return false;
    } finally {
      setBusy(null);
    }
  };

  if (query.error && !project) {
    return (
      <section className="panel result-panel detail-panel">
        <div className="empty">
          <span className="empty-icon" aria-hidden="true">!</span>
          <h3>项目读取失败</h3>
          <p>{query.error}</p>
          <button className="btn btn-secondary" type="button" onClick={query.refresh}>重试</button>
        </div>
      </section>
    );
  }

  if (!project) {
    return (
      <section className="panel result-panel detail-panel react-detail-loading" aria-live="polite">
        <div className="empty">
          <span className="empty-icon" aria-hidden="true">◧</span>
          <h3>正在加载项目</h3>
          <p>读取镜头、任务状态和创作底稿。</p>
        </div>
      </section>
    );
  }

  const progress = Math.round((project.job?.progress ?? 0) * 100);
  const shots = project.shots;
  const canDownload = project.status === "done";

  return (
    <section className="panel result-panel detail-panel" id="detail" aria-live="polite">
      <div className="result-head">
        <div>
          <p className="panel-kicker">ANALYSIS RESULT</p>
          <h2>{project.title}</h2>
          <p>{project.width}×{project.height} · {formatNumber(project.duration, 1)}s · {formatNumber(project.fps, 1)} fps</p>
        </div>
        <div className="result-actions">
          <span className="status-pill" data-status={project.status}>{STATUS_LABELS[project.status] ?? project.status}</span>
          {running ? (
            <button
              className="btn btn-ghost danger-action"
              type="button"
              disabled={busy !== null}
              onClick={() => {
                if (window.confirm("确定取消当前分析任务？")) {
                  void run("cancel", () => cancelProject(project.id), "分析任务已取消");
                }
              }}
            >
              取消分析
            </button>
          ) : project.status === "failed" || project.status === "cancelled" ? (
            <button
              className="btn btn-primary"
              type="button"
              disabled={busy !== null}
              onClick={() => { void run("retry", () => reanalyzeProject(project.id), "已重新开始分析"); }}
            >
              重新分析
            </button>
          ) : null}
          {canDownload ? <a className="btn btn-secondary" href={project.recipe_url} download>下载 VIDEO.md</a> : null}
          {canDownload ? <a className="btn btn-ghost" href={`${project.recipe_url}?format=json`} download>JSON</a> : null}
          <button
            className="btn btn-ghost danger-action"
            type="button"
            disabled={busy !== null}
            onClick={() => {
              if (window.confirm("确定删除这个项目及其文件？")) {
                void run("delete", () => deleteProject(project.id), "项目已删除").then((deleted) => {
                  if (deleted) {
                    navigate("/reverse");
                  }
                });
              }
            }}
          >
            删除项目
          </button>
        </div>
      </div>

      {shots.length > 0 ? <Summary project={project} /> : null}
      <Usage projectId={project.id} />

      {running ? (
        <div className="progress-card">
          <div className="progress-head">
            <span>{STEP_HINTS[project.job?.step ?? ""] || "处理中"}</span>
            <span>{progress}%</span>
          </div>
          <div className="progress-track"><i style={{ width: `${progress}%` }} /></div>
          <p className="muted">{project.job?.step || "queued"}</p>
        </div>
      ) : null}

      {project.status === "failed" || project.status === "cancelled" ? (
        <div className="error-card">
          {project.job?.error || (project.status === "cancelled" ? "任务已取消" : "分析失败，请重试")}
        </div>
      ) : null}

      <div className="analysis-media">
        <div className="media-card">
          <div className="media-card-head"><span>SOURCE VIDEO</span><b>PREVIEW</b></div>
          <div className="video-pane"><video ref={videoRef} controls preload="metadata" src={project.video_url} /></div>
        </div>
        <div className="media-card">
          <div className="media-card-head"><span>CREATIVE RECIPE</span><b>MARKDOWN</b></div>
          <div className="recipe-pane"><pre>{recipeText || (running ? "正在生成创作底稿…" : "暂无创作底稿")}</pre></div>
        </div>
      </div>

      <TimelineEditor
        project={project}
        running={running}
        onMutated={() => {
          query.refresh();
          onChanged();
        }}
        onSeek={(seconds) => {
          const video = videoRef.current;
          if (!video) {
            return;
          }
          try {
            video.currentTime = Math.max(0, seconds);
          } catch {
            // Some browsers reject seeks before metadata is available.
          }
        }}
      />

      {shots.length > 0 ? (
        <>
          <div className="section-bar">
            <div><span>STORYBOARD / {shots.length} SCENES</span><h3>镜头拆解</h3></div>
          </div>
          <div className="shot-list">
            {shots.map((shot, index) => <ShotCard key={shot.id} shot={shot} position={index} project={project} />)}
          </div>
        </>
      ) : running ? (
        <div className="empty">
          <span className="empty-icon" aria-hidden="true">◧</span>
          <h3>正在分析镜头</h3>
          <p>镜头切分与画面分析完成后会自动显示在这里。</p>
        </div>
      ) : (
        <div className="empty">
          <span className="empty-icon" aria-hidden="true">◧</span>
          <h3>暂无镜头结果</h3>
          <p>分析尚未产出镜头数据，请查看任务状态或重新上传。</p>
        </div>
      )}
    </section>
  );
}
