import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import {
  cancelProject,
  deleteProject,
  fetchProject,
  fetchProjectCost,
  reanalyzeProject,
} from "../../api/endpoints";
import type { JobStatus, ProjectDetail as ProjectDetailData, Shot } from "../../api/types";
import { Icon } from "../../components/Icon";
import { StatusBadge } from "../../components/StatusBadge";
import { useApiQuery } from "../../hooks/useApiQuery";
import { useJobEvents } from "../../hooks/useJobEvents";
import { useUiStore } from "../../store/uiStore";
import { formatClock, formatCost, formatNumber, ORIGIN_LABELS } from "../../utils/format";
import { ShotCard } from "./ShotCard";
import { TimelineEditor } from "./TimelineEditor";

const STEP_HINTS: Record<string, string> = {
  probing: "正在读取视频信息",
  segmenting: "正在检测镜头切换",
  extracting: "正在抽取关键帧",
  transcribing: "正在转写音频",
  analyzing: "正在逐镜分析画面",
  fusing: "正在汇总分镜与节奏",
  done: "分析完成",
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
  const lighting = shots.map((shot) => shot.analysis.lighting).find(Boolean);
  const style = first?.visual_style || first?.shot_type || "等待画面分析";
  return (
    <div className="rr-summary-list">
      <div className="rr-summary-item">
        <span className="rr-summary-icon"><Icon name="chart" size={15} /></span>
        <div>
          <strong>节奏：{shots.length} 个镜头，平均 {average} 秒</strong>
          <span>先看整体剪辑密度，再决定新片子的开场与推进速度。</span>
        </div>
      </div>
      <div className="rr-summary-item">
        <span className="rr-summary-icon"><Icon name="sun" size={15} /></span>
        <div>
          <strong>视觉：{style}</strong>
          <span>{lightspeedCopy(lighting, first?.scene)}</span>
        </div>
      </div>
      <div className="rr-summary-item">
        <span className="rr-summary-icon"><Icon name="layers" size={15} /></span>
        <div>
          <strong>色彩：{palette.length ? `${palette.length} 个主色` : "等待色板"}</strong>
          <div className="rr-palette" aria-label="主色板">
            {palette.length
              ? palette.map((color, index) => <i style={{ background: color }} key={`${color}-${index}`} />)
              : <span className="rr-muted-copy">分析完成后自动提取</span>}
          </div>
        </div>
      </div>
    </div>
  );
}

function lightspeedCopy(lighting: string | undefined, scene: string | undefined): string {
  if (lighting && scene) {
    return `${lighting} · ${scene}。可以直接沿用这组画面语言。`;
  }
  return lighting || scene || "分析完成后给出光线、场景和镜头语言建议。";
}

function Usage({ projectId }: { projectId: string }) {
  const costQuery = useApiQuery((signal) => fetchProjectCost(projectId, signal), [projectId]);
  const data = costQuery.data;
  if (!data) {
    return null;
  }
  return (
    <div className="rr-usage-grid">
      <div><span>调用次数</span><strong>{formatNumber(data.cost.calls, 0)}</strong></div>
      <div><span>输入 Token</span><strong>{formatNumber(data.cost.prompt_tokens, 0)}</strong></div>
      <div><span>输出 Token</span><strong>{formatNumber(data.cost.completion_tokens, 0)}</strong></div>
      <div><span>预估费用</span><strong>{formatCost(data.cost)}</strong><small>{data.cost.note || "估算值"}</small></div>
    </div>
  );
}

function ExecutionNotice({ metrics }: { metrics: Record<string, unknown> | undefined }) {
  if (!metrics) {
    return null;
  }
  const mode = typeof metrics.analysis_mode === "string" ? metrics.analysis_mode : "";
  const degraded = metrics.degraded === true;
  const asrStatus = typeof metrics.asr_status === "string" ? metrics.asr_status : "";
  const reasons = Array.isArray(metrics.degradation_reasons)
    ? metrics.degradation_reasons.filter((item): item is string => typeof item === "string")
    : [];
  if (mode !== "mock" && !degraded && asrStatus !== "failed") {
    return null;
  }
  const label = degraded ? "本次分析发生降级" : mode === "mock" ? "本次分析使用 Mock 模式" : "语音转写失败";
  return (
    <div className={`execution-notice${degraded ? " is-degraded" : ""}`} role="status">
      <Icon name="alert" size={17} />
      <strong>{label}</strong>
      {mode === "mock" ? <span>未调用真实模型，镜头内容与提示词仅用于流程验证。</span> : null}
      {asrStatus === "failed" ? <span>ASR 未完成，台词字段可能为空。</span> : null}
      {reasons.length ? <span>{reasons.slice(0, 2).join("；")}</span> : null}
    </div>
  );
}

function ShotFocus({ shot, position, project }: { shot: Shot; position: number; project: ProjectDetailData }) {
  const showToast = useUiStore((state) => state.showToast);
  const analysis = shot.analysis;
  const index = String(shot.index).padStart(2, "0");
  const palette = analysis.color_palette ?? [];
  const tags = [analysis.shot_type, analysis.camera_movement, analysis.lighting].filter((item): item is string => Boolean(item));

  const copyPrompt = async () => {
    if (!analysis.prompt) {
      return;
    }
    try {
      await navigator.clipboard.writeText(analysis.prompt);
      showToast("Prompt 已复制", "success");
    } catch {
      showToast("复制失败，请手动选择文本", "error");
    }
  };

  return (
    <section className="rr-card rr-shot-focus" aria-labelledby="shot-focus-title">
      <div className="rr-shot-focus-copy">
        <p className="rr-eyebrow">SHOT {index} / {formatClock(shot.start_s)}–{formatClock(shot.end_s)}</p>
        <div className="rr-shot-focus-title">
          <h2 id="shot-focus-title">{analysis.subject || analysis.shot_type || `镜头 ${index}`}</h2>
          <span className="rr-shot-position">{String(position + 1).padStart(2, "0")} / {String(project.shots.length).padStart(2, "0")}</span>
        </div>
        <p>{analysis.remake_notes || analysis.scene || analysis.visual_style || "这个镜头还没有补充说明。"}</p>
        <div className="rr-tag-row">
          {tags.map((tag) => <span className="rr-tag" key={tag}>{tag}</span>)}
          {shot.origin ? <span className="rr-tag is-soft">{ORIGIN_LABELS[shot.origin] ?? shot.origin}</span> : null}
        </div>
      </div>

      <div className="rr-shot-stats">
        <div><strong>{formatNumber(shot.end_s - shot.start_s, 1)}s</strong><span>时长</span></div>
        <div><strong>{analysis.shot_type || "—"}</strong><span>景别</span></div>
        <div><strong>{analysis.camera_movement || "固定"}</strong><span>运镜</span></div>
      </div>

      <div className="rr-prompt-block">
        <div className="rr-prompt-block-head">
          <span>PROMPT</span>
          <button className="rr-text-btn" type="button" onClick={copyPrompt} disabled={!analysis.prompt}>
            <Icon name="copy" size={14} /> 复制
          </button>
        </div>
        <p>{analysis.prompt || "该镜头暂未生成 Prompt。"}</p>
      </div>

      <div className="rr-shot-focus-foot">
        <div className="rr-palette">
          {palette.map((color, colorIndex) => <i style={{ background: color }} key={`${color}-${colorIndex}`} />)}
          <span>{analysis.visual_style || "镜头色板"}</span>
        </div>
        <Link className="rr-btn rr-btn-secondary rr-btn-sm" to={`/generate?reference=${encodeURIComponent(project.id)}&mode=full`}>
          用此镜头生成 <Icon name="arrow-right" size={14} />
        </Link>
      </div>
    </section>
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
  const [selectedShotId, setSelectedShotId] = useState<number | null>(null);
  const previousStatus = useRef<JobStatus | null>(null);

  useJobEvents(project?.job?.id, running, query.refresh);

  useEffect(() => {
    if (!project?.shots.length) {
      setSelectedShotId(null);
      return;
    }
    if (!project.shots.some((shot) => shot.id === selectedShotId)) {
      setSelectedShotId(project.shots[0].id);
    }
  }, [project, selectedShotId]);

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
      <section className="rr-card rr-message-card">
        <div className="rr-inline-empty is-error">
          <Icon name="alert" size={26} />
          <strong>项目读取失败</strong>
          <p>{query.error}</p>
          <button className="rr-btn rr-btn-secondary" type="button" onClick={query.refresh}>重新加载</button>
        </div>
      </section>
    );
  }

  if (!project) {
    return (
      <section className="rr-card rr-message-card" aria-live="polite">
        <div className="rr-inline-empty">
          <Icon name="refresh" size={26} className="is-spinning" />
          <strong>正在加载项目</strong>
          <p>读取镜头、任务状态和创作底稿。</p>
        </div>
      </section>
    );
  }

  const progress = Math.round((project.job?.progress ?? 0) * 100);
  const shots = project.shots;
  const canDownload = project.status === "done";
  const selectedShot = shots.find((shot) => shot.id === selectedShotId) ?? shots[0];
  const selectedPosition = selectedShot ? shots.findIndex((shot) => shot.id === selectedShot.id) : -1;
  const createdAt = project.created_at ? new Date(project.created_at).toLocaleDateString("zh-CN", { year: "numeric", month: "long", day: "numeric" }) : "";

  const seekTo = (seconds: number) => {
    const video = videoRef.current;
    if (!video) {
      return;
    }
    try {
      video.currentTime = Math.max(0, seconds);
    } catch {
      // Some browsers reject seeks before metadata is available.
    }
  };

  return (
    <div className="rr-project-detail" id="detail" aria-live="polite">
      <div className="rr-breadcrumb">
        <Link to="/reverse"><Icon name="arrow-left" size={14} /> 全部项目</Link>
        <span>/</span>
        <span>{project.title}</span>
      </div>

      <header className="rr-project-header">
        <div className="rr-project-heading">
          <div className="rr-project-title-line">
            <h1>{project.title}</h1>
            <StatusBadge status={project.status} />
          </div>
          <div className="rr-project-meta-line">
            <span>{project.width} × {project.height}</span>
            <span>{formatNumber(project.duration, 1)} 秒</span>
            <span>{shots.length} 个镜头</span>
            <span>{formatNumber(project.fps, 1)} fps</span>
            {createdAt ? <span>{createdAt}</span> : null}
          </div>
        </div>
        <div className="rr-project-actions">
          {canDownload ? (
            <Link className="rr-btn rr-btn-primary" to={`/generate?reference=${encodeURIComponent(project.id)}&mode=full`}>
              <Icon name="sparkles" size={16} /> 生成提示词
            </Link>
          ) : null}
          {running ? (
            <button
              className="rr-btn rr-btn-secondary"
              type="button"
              disabled={busy !== null}
              onClick={() => {
                if (window.confirm("确定取消当前分析任务？")) {
                  void run("cancel", () => cancelProject(project.id), "分析任务已取消");
                }
              }}
            >
              <Icon name="clock" size={15} /> 取消分析
            </button>
          ) : project.status === "failed" || project.status === "cancelled" ? (
            <button
              className="rr-btn rr-btn-primary"
              type="button"
              disabled={busy !== null}
              onClick={() => { void run("retry", () => reanalyzeProject(project.id), "已重新开始分析"); }}
            >
              <Icon name="refresh" size={15} /> 重新分析
            </button>
          ) : null}
          {canDownload ? <a className="rr-btn rr-btn-secondary" href={project.recipe_url} download><Icon name="download" size={15} /> 创作底稿</a> : null}
          <details className="rr-more-menu">
            <summary className="rr-btn rr-btn-ghost" aria-label="更多项目操作"><Icon name="more" size={17} /></summary>
            <div className="rr-more-menu-panel">
              {canDownload ? <a href={`${project.recipe_url}?format=json`} download><Icon name="document" size={15} /> 下载 JSON</a> : null}
              <button
                type="button"
                className="is-danger"
                disabled={busy !== null}
                onClick={() => {
                  if (window.confirm("确定删除这个项目及其文件？此操作不可恢复。")) {
                    void run("delete", () => deleteProject(project.id), "项目已删除").then((deleted) => {
                      if (deleted) {
                        navigate("/reverse");
                      }
                    });
                  }
                }}
              >
                <Icon name="trash" size={15} /> 删除项目
              </button>
            </div>
          </details>
        </div>
      </header>

      <ExecutionNotice metrics={project.job?.metrics} />

      {running ? (
        <div className="rr-analysis-progress">
          <span className="rr-progress-icon"><Icon name="refresh" size={19} className="is-spinning" /></span>
          <div className="rr-progress-copy">
            <strong>{STEP_HINTS[project.job?.step ?? ""] || "正在处理视频"}</strong>
            <span>分析会在后台继续运行，可以离开页面稍后回来查看。</span>
          </div>
          <div className="rr-progress-value"><b>{progress}%</b><span>{project.job?.step || "queued"}</span></div>
          <div className="rr-progress-track"><i style={{ width: `${progress}%` }} /></div>
        </div>
      ) : null}

      {project.status === "failed" || project.status === "cancelled" ? (
        <div className="rr-inline-empty is-error rr-error-panel">
          <Icon name="alert" size={24} />
          <strong>{project.status === "cancelled" ? "任务已取消" : "分析失败"}</strong>
          <p>{project.job?.error || "可以重新提交分析，或返回项目列表检查源视频。"}</p>
        </div>
      ) : null}

      <div className="rr-workspace-grid" id="overview">
        <div className="rr-workspace-main">
          <section className="rr-card rr-player-card" aria-label="原始视频与镜头缩略图">
            <div className="rr-player-head">
              <span>原始视频</span>
              <b>PREVIEW · {shots.length} SHOTS</b>
            </div>
            <div className="rr-video-frame"><video ref={videoRef} controls preload="metadata" src={project.video_url} /></div>
            {shots.length ? (
              <div className="rr-shot-strip" aria-label="镜头缩略图">
                {shots.map((shot) => (
                  <button
                    key={shot.id}
                    type="button"
                    className={`rr-shot-thumb${shot.id === selectedShot?.id ? " is-active" : ""}`}
                    onClick={() => { setSelectedShotId(shot.id); seekTo(shot.start_s); }}
                    aria-label={`镜头 ${shot.index}，${formatClock(shot.start_s)}`}
                    aria-pressed={shot.id === selectedShot?.id}
                  >
                    {shot.keyframe_url ? <img src={shot.keyframe_url} alt="" loading="lazy" /> : <span><Icon name="film" size={18} /></span>}
                    <b>{String(shot.index).padStart(2, "0")}</b>
                  </button>
                ))}
              </div>
            ) : null}
          </section>

          {selectedShot ? <ShotFocus shot={selectedShot} position={selectedPosition} project={project} /> : null}

          <details className="rr-card rr-fold rr-timeline-fold" id="timeline">
            <summary>
              <span className="rr-fold-icon"><Icon name="layers" size={17} /></span>
              <span><strong>镜头时间轴与边界微调</strong><small>拖拽分界、拆分、合并或局部重分析</small></span>
              <Icon name="chevron-down" size={16} />
            </summary>
            <div className="rr-fold-body">
              <TimelineEditor
                project={project}
                running={running}
                onMutated={() => {
                  query.refresh();
                  onChanged();
                }}
                onSeek={seekTo}
              />
            </div>
          </details>

          <details className="rr-card rr-fold">
            <summary>
              <span className="rr-fold-icon"><Icon name="document" size={17} /></span>
              <span><strong>创作底稿与用量</strong><small>Markdown 底稿、Token 与费用估算</small></span>
              <Icon name="chevron-down" size={16} />
            </summary>
            <div className="rr-fold-body">
              <div className="rr-recipe-pane"><pre>{recipeText || (running ? "正在生成创作底稿…" : "暂无创作底稿")}</pre></div>
              <Usage projectId={project.id} />
            </div>
          </details>
        </div>

        <aside className="rr-workspace-side">
          <section className="rr-card rr-summary-card" aria-labelledby="summary-title">
            <p className="rr-eyebrow">AI SUMMARY</p>
            <h2 id="summary-title">这条片子为什么有效</h2>
            {shots.length ? <Summary project={project} /> : <p className="rr-muted-copy">镜头分析完成后，这里会自动总结节奏、视觉和色彩特征。</p>}
            {canDownload ? (
              <Link className="rr-btn rr-btn-dark" to={`/generate?reference=${encodeURIComponent(project.id)}&mode=full`}>
                用这套结构生成新方案 <Icon name="arrow-right" size={14} />
              </Link>
            ) : null}
          </section>

          {shots.length ? (
            <section className="rr-card rr-shot-index" aria-labelledby="index-title">
              <div className="rr-shot-index-head"><h2 id="index-title">全部镜头</h2><span>{String(shots.length).padStart(2, "0")} SHOTS</span></div>
              <div className="rr-index-list">
                {shots.map((shot) => (
                  <button
                    key={shot.id}
                    type="button"
                    className={`rr-index-row${shot.id === selectedShot?.id ? " is-active" : ""}`}
                    onClick={() => { setSelectedShotId(shot.id); seekTo(shot.start_s); }}
                  >
                    <span className="rr-index-poster">
                      {shot.keyframe_url ? <img src={shot.keyframe_url} alt="" loading="lazy" /> : <Icon name="film" size={14} />}
                    </span>
                    <span className="rr-index-copy">
                      <strong>{shot.analysis.subject || shot.analysis.shot_type || `镜头 ${shot.index}`}</strong>
                      <small>{formatClock(shot.start_s)}–{formatClock(shot.end_s)}</small>
                    </span>
                    <span className="rr-index-number">{String(shot.index).padStart(2, "0")}</span>
                  </button>
                ))}
              </div>
            </section>
          ) : null}
        </aside>
      </div>

      <section className="rr-storyboard" id="shots">
        {shots.length > 0 ? (
          <>
            <div className="rr-section-heading">
              <div><p className="rr-eyebrow">STORYBOARD</p><h2>逐镜拆解</h2></div>
              <span className="rr-count-badge">{shots.length} 个镜头</span>
            </div>
            <div className="rr-shot-list">
              {shots.map((shot, index) => <ShotCard key={shot.id} shot={shot} position={index} project={project} />)}
            </div>
          </>
        ) : running ? (
          <div className="rr-inline-empty">
            <Icon name="film" size={26} />
            <strong>正在分析镜头</strong>
            <p>镜头切分和画面分析完成后会自动显示在这里。</p>
          </div>
        ) : (
          <div className="rr-inline-empty">
            <Icon name="film" size={26} />
            <strong>暂无镜头结果</strong>
            <p>分析尚未产出镜头数据，可以重新分析或上传其他视频。</p>
          </div>
        )}
      </section>
    </div>
  );
}

