import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";

import {
  createPromptProject,
  fetchGenerationJobs,
  fetchPromptProject,
  fetchPromptProjects,
  fetchProjects,
  regeneratePromptProject,
  startGeneration,
} from "../../api/endpoints";
import type { GenerationJob, PromptBrief, PromptProject, PromptShot } from "../../api/types";
import { Icon } from "../../components/Icon";
import { StatusBadge } from "../../components/StatusBadge";
import { useApiQuery } from "../../hooks/useApiQuery";
import { useUiStore } from "../../store/uiStore";

const TARGET_MODELS = [
  { value: "generic", label: "通用模型" },
  { value: "veo", label: "Veo" },
  { value: "kling", label: "可灵" },
  { value: "runway", label: "Runway" },
  { value: "pika", label: "Pika" },
] as const;

const ASPECT_RATIOS = ["16:9", "9:16", "1:1", "4:5"] as const;

const TEMPLATES = [
  {
    label: "产品广告",
    idea: "为一家精品咖啡品牌拍摄 15 秒产品广告，突出咖啡豆研磨、手冲和成品的质感，画面克制高级，最后落在品牌标识上。",
    style: "温暖自然光，木质桌面，浅景深，干净克制",
    shot_count: 4,
    duration_s: 15,
  },
  {
    label: "人物短片",
    idea: "一名年轻设计师在清晨的城市里散步，从疲惫到重新找到灵感，用三个生活片段讲一个安静但有力量的小故事。",
    style: "胶片颗粒，柔和逆光，低饱和，轻微手持感",
    shot_count: 5,
    duration_s: 20,
  },
  {
    label: "品牌氛围",
    idea: "用抽象的光影、材质和水面反射传递科技品牌的未来感，不出现具体人物，节奏舒缓，适合官网首屏。",
    style: "未来感，冷色调，微距材质，体积光，电影质感",
    shot_count: 4,
    duration_s: 12,
  },
] as const;

const GENERATION_STATUS: Record<string, string> = {
  queued: "排队中",
  running: "生成中",
  succeeded: "已完成",
  partial: "部分完成",
  failed: "失败",
  cancelled: "已取消",
};

function isRunning(status: string | undefined): boolean {
  return status === "queued" || status === "running";
}

function modeNotice(metrics: Record<string, unknown> | undefined) {
  if (!metrics) {
    return null;
  }
  const mode = metrics.analysis_mode;
  const degraded = metrics.degraded === true;
  if (mode !== "mock" && !degraded) {
    return null;
  }
  const reasons = Array.isArray(metrics.degradation_reasons)
    ? metrics.degradation_reasons.filter((item): item is string => typeof item === "string")
    : [];
  return (
    <div className={`execution-notice${degraded ? " is-degraded" : ""}`} role="status">
      <Icon name="alert" size={17} />
      <strong>{degraded ? "提示词生成发生降级" : "当前提示词使用 Mock 模式"}</strong>
      <span>{degraded ? reasons.slice(0, 2).join("；") : "未调用真实文本模型，仅用于验证流程。"}</span>
    </div>
  );
}

function generationLabel(status: string): string {
  return GENERATION_STATUS[status] ?? status;
}

async function copyText(value: string, showToast: (message: string, tone?: "default" | "success" | "error") => void, message: string) {
  try {
    await navigator.clipboard.writeText(value);
    showToast(message, "success");
  } catch {
    showToast("复制失败，请手动选择文本", "error");
  }
}

function PromptShotItem({ shot, onCopy }: { shot: PromptShot; onCopy: (shot: PromptShot) => void }) {
  const index = String(shot.index).padStart(2, "0");
  return (
    <article className="rr-prompt-shot-item">
      <header className="rr-prompt-shot-head">
        <span className="rr-prompt-shot-number">{index}</span>
        <div className="rr-prompt-shot-title">
          <strong>{shot.subject || shot.shot_type || `镜头 ${index}`}</strong>
          <span>{shot.shot_type || "镜头"} · {shot.start_s.toFixed(1)}–{shot.end_s.toFixed(1)} 秒 · {shot.camera_movement || "固定机位"}</span>
        </div>
        <button className="rr-icon-btn" type="button" onClick={() => onCopy(shot)} aria-label={`复制镜头 ${index} 的提示词`}>
          <Icon name="copy" size={16} />
        </button>
      </header>
      <div className="rr-prompt-shot-copy">
        <span>PROMPT</span>
        <p>{shot.prompt || "该镜头暂未生成提示词。"}</p>
      </div>
      <div className="rr-tag-row">
        {[shot.scene, shot.lighting, shot.transition].filter(Boolean).map((item, index) => <span className="rr-tag is-soft" key={`${item}-${index}`}>{item}</span>)}
      </div>
      {shot.negative_prompt ? (
        <details className="rr-prompt-negative">
          <summary>查看负向提示词</summary>
          <p>{shot.negative_prompt}</p>
        </details>
      ) : null}
    </article>
  );
}

function PromptDetail({ project }: { project: PromptProject }) {
  const showToast = useUiStore((state) => state.showToast);
  const jobsQuery = useApiQuery(
    (signal) => fetchGenerationJobs(project.id, signal),
    [project.id],
  );
  const [busy, setBusy] = useState("");
  const plan = project.plan;
  const planShots = plan?.shots ?? [];
  const activeJobs = jobsQuery.data?.some((job) => isRunning(job.status)) ?? false;

  useEffect(() => {
    if (!activeJobs) {
      return undefined;
    }
    const timer = window.setInterval(jobsQuery.refresh, 2800);
    return () => window.clearInterval(timer);
  }, [activeJobs, jobsQuery.refresh]);

  const run = async (label: string, operation: () => Promise<unknown>, message: string) => {
    setBusy(label);
    try {
      await operation();
      showToast(message, "success");
      jobsQuery.refresh();
    } catch (error) {
      showToast(error instanceof Error ? error.message : "操作失败", "error");
    } finally {
      setBusy("");
    }
  };

  const copyAll = () => {
    const text = planShots.map((shot) => (
      `SHOT ${String(shot.index).padStart(2, "0")} · ${shot.start_s.toFixed(1)}–${shot.end_s.toFixed(1)}s\n${shot.prompt}`
    )).join("\n\n");
    if (text) {
      void copyText(text, showToast, "全部镜头提示词已复制");
    }
  };

  return (
    <section className="rr-card rr-plan-card" aria-labelledby="plan-title">
      <header className="rr-plan-head">
        <div>
          <p className="rr-eyebrow">PROMPT PLAN</p>
          <div className="rr-plan-title-line">
            <h2 id="plan-title">{project.title}</h2>
            <StatusBadge status={project.status} />
          </div>
          <p>{project.shot_count} 个镜头 · 版本 {project.version_count} · 目标模型 {project.target_model || "通用"}</p>
        </div>
        <div className="rr-plan-actions">
          {isRunning(project.status) ? (
            <span className="rr-running-label"><Icon name="refresh" size={15} className="is-spinning" /> 正在生成 {Math.round(project.progress * 100)}%</span>
          ) : null}
          {project.status === "done" ? (
            <button
              className="rr-btn rr-btn-primary"
              type="button"
              disabled={Boolean(busy)}
              onClick={() => void run("generate", () => startGeneration(project.id), "视频生成任务已排队")}
            >
              <Icon name="video" size={16} /> 生成视频
            </button>
          ) : null}
          <a className="rr-btn rr-btn-secondary" href={project.export_url} download><Icon name="download" size={15} /> 导出 Markdown</a>
          <details className="rr-more-menu">
            <summary className="rr-btn rr-btn-ghost" aria-label="更多方案操作"><Icon name="more" size={17} /></summary>
            <div className="rr-more-menu-panel">
              <button
                type="button"
                disabled={Boolean(busy) || isRunning(project.status)}
                onClick={() => void run("regenerate", () => regeneratePromptProject(project.id), "已重新开始生成")}
              >
                <Icon name="refresh" size={15} /> 重新生成方案
              </button>
              <a href={`${project.export_url}?format=json`} download><Icon name="document" size={15} /> 下载 JSON</a>
            </div>
          </details>
        </div>
      </header>

      {isRunning(project.status) ? (
        <div className="rr-plan-progress">
          <div><strong>正在生成分镜与提示词</strong><span>{Math.round(project.progress * 100)}%</span></div>
          <div className="rr-progress-track"><i style={{ width: `${Math.round(project.progress * 100)}%` }} /></div>
          <p>页面会自动刷新，完成后可以直接导出或生成视频。</p>
        </div>
      ) : null}

      {modeNotice(project.metrics)}
      {project.error ? <div className="rr-inline-empty is-error rr-error-panel"><Icon name="alert" size={22} /><strong>生成失败</strong><p>{project.error}</p></div> : null}

      {plan ? (
        <>
          <div className="rr-plan-overview">
            <div><span>整体风格</span><strong>{plan.global_style || "未指定"}</strong></div>
            <div><span>目标模型</span><strong>{TARGET_MODELS.find((item) => item.value === plan.target_model)?.label ?? plan.target_model}</strong></div>
            <div><span>总时长</span><strong>{plan.duration_s} 秒</strong></div>
            <div><span>画面比例</span><strong>{plan.aspect_ratio}</strong></div>
          </div>
          {plan.summary ? <p className="rr-plan-summary">{plan.summary}</p> : null}
          {plan.warnings?.length ? (
            <div className="execution-notice is-degraded">
              <Icon name="alert" size={17} />
              <strong>生成提示</strong>
              <span>{plan.warnings.slice(0, 3).join("；")}</span>
            </div>
          ) : null}

          <div className="rr-section-heading rr-plan-list-head">
            <div><p className="rr-eyebrow">SHOT PROMPTS</p><h3>分镜提示词</h3></div>
            <button className="rr-btn rr-btn-ghost rr-btn-sm" type="button" onClick={copyAll}><Icon name="copy" size={15} /> 复制全部</button>
          </div>
          {planShots.length ? (
            <div className="rr-prompt-shot-list">
              {planShots.map((shot) => (
                <PromptShotItem
                  key={shot.index}
                  shot={shot}
                  onCopy={(item) => void copyText(item.prompt, showToast, `镜头 ${String(item.index).padStart(2, "0")} 已复制`)}
                />
              ))}
            </div>
          ) : (
            <div className="rr-inline-empty"><Icon name="sparkles" size={26} /><strong>方案还没有分镜内容</strong><p>可以尝试重新生成。</p></div>
          )}
        </>
      ) : !isRunning(project.status) && !project.error ? (
        <div className="rr-inline-empty"><Icon name="sparkles" size={26} /><strong>方案还没有可用内容</strong><p>可以尝试重新生成。</p></div>
      ) : null}

      {jobsQuery.data?.length ? (
        <section className="rr-generation-history">
          <div className="rr-section-heading">
            <div><p className="rr-eyebrow">VIDEO JOBS</p><h3>视频生成记录</h3></div>
            <button className="rr-icon-btn" type="button" onClick={jobsQuery.refresh} aria-label="刷新生成记录"><Icon name="refresh" size={16} /></button>
          </div>
          <div className="rr-generation-list">
            {jobsQuery.data.map((job: GenerationJob) => {
              const resultShots = job.result?.shots ?? [];
              return (
                <article className="rr-generation-job" key={job.id} data-status={job.status}>
                  <div className="rr-generation-job-top">
                    <div><strong>{job.provider} · {job.model}</strong><span>{generationLabel(job.status)}</span></div>
                    <span>{Math.round(job.progress * 100)}%</span>
                  </div>
                  {isRunning(job.status) ? <div className="rr-progress-track"><i style={{ width: `${Math.round(job.progress * 100)}%` }} /></div> : null}
                  {job.error ? <p className="rr-generation-error">{job.error}</p> : null}
                  {resultShots.length ? (
                    <div className="rr-generation-results">
                      {resultShots.map((shot) => (
                        <span className={`rr-generation-result is-${shot.status}`} key={shot.shot_index}>
                          镜头 {shot.shot_index}
                          {shot.download_url ? <a href={shot.download_url} target="_blank" rel="noreferrer">查看</a> : <small>{shot.error || "处理中"}</small>}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </article>
              );
            })}
          </div>
        </section>
      ) : null}
    </section>
  );
}

function PromptLibrary({
  projects,
  selectedId,
  loading,
  onSelect,
  onCreate,
}: {
  projects: PromptProject[];
  selectedId: string;
  loading: boolean;
  onSelect: (id: string) => void;
  onCreate: () => void;
}) {
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return projects.filter((project) => !needle || project.title.toLowerCase().includes(needle));
  }, [projects, query]);

  return (
    <section className="rr-card rr-plan-library" aria-labelledby="library-title">
      <div className="rr-card-head">
        <div><p className="rr-eyebrow">PLAN LIBRARY</p><h2 id="library-title">方案库</h2></div>
        <div className="rr-card-actions">
          <span className="rr-count-badge">{String(projects.length).padStart(2, "0")}</span>
          <button className="rr-icon-btn is-accent" type="button" onClick={onCreate} aria-label="新建提示词方案"><Icon name="plus" size={17} /></button>
        </div>
      </div>
      <label className="rr-search-field">
        <Icon name="search" size={16} />
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索方案" aria-label="搜索提示词方案" />
      </label>
      <div className="rr-plan-library-list">
        {loading && !projects.length ? (
          <div className="rr-inline-empty"><Icon name="refresh" size={22} className="is-spinning" /><p>正在加载方案…</p></div>
        ) : filtered.length === 0 ? (
          <div className="rr-inline-empty"><Icon name="folder" size={22} /><strong>{projects.length ? "没有匹配的方案" : "还没有提示词方案"}</strong><p>{projects.length ? "换个关键词试试。" : "填写左侧简报即可生成第一份方案。"}</p></div>
        ) : filtered.map((project) => (
          <button className={`rr-plan-library-row${project.id === selectedId ? " is-selected" : ""}`} type="button" key={project.id} onClick={() => onSelect(project.id)}>
            <span className="rr-plan-library-icon"><Icon name="sparkles" size={17} /></span>
            <span className="rr-plan-library-copy">
              <strong>{project.title || "未命名方案"}</strong>
              <small>{project.shot_count} 个镜头 · {project.version_count} 个版本</small>
            </span>
            <StatusBadge status={project.status} />
          </button>
        ))}
      </div>
    </section>
  );
}

export function GeneratePage() {
  const showToast = useUiStore((state) => state.showToast);
  const [searchParams, setSearchParams] = useSearchParams();
  const initialReference = searchParams.get("reference") || "";
  const initialMode = searchParams.get("mode") === "full" ? "full" : "style";
  const projectsQuery = useApiQuery((signal) => fetchPromptProjects(signal), []);
  const reverseQuery = useApiQuery((signal) => fetchProjects(signal), []);
  const [selectedId, setSelectedId] = useState(searchParams.get("project") || "");
  const detailQuery = useApiQuery(
    (signal) => (selectedId ? fetchPromptProject(selectedId, signal) : Promise.resolve(null)),
    [selectedId],
  );
  const [creating, setCreating] = useState(false);
  const [brief, setBrief] = useState({
    title: "",
    idea: "",
    target_model: "generic",
    language: "zh" as "zh" | "en",
    duration_s: 15,
    aspect_ratio: "16:9",
    shot_count: 4,
    style: "",
    mood: "",
    negative_prompt: "",
    reference_project_id: initialReference,
    reference_mode: initialMode as "style" | "structure" | "full",
  });

  const selected = detailQuery.data;
  const selectedRunning = isRunning(selected?.status);

  useEffect(() => {
    if (!selectedId && projectsQuery.data?.length) {
      setSelectedId(projectsQuery.data[0].id);
    }
  }, [projectsQuery.data, selectedId]);

  useEffect(() => {
    if (!selectedRunning) {
      return undefined;
    }
    const timer = window.setInterval(() => {
      detailQuery.refresh();
      projectsQuery.refresh();
    }, 2500);
    return () => window.clearInterval(timer);
  }, [detailQuery.refresh, projectsQuery.refresh, selectedRunning]);

  const selectProject = (id: string) => {
    setSelectedId(id);
    const next = new URLSearchParams(searchParams);
    next.set("project", id);
    setSearchParams(next, { replace: true });
  };

  const focusBrief = () => {
    document.getElementById("brief-form")?.scrollIntoView({ behavior: "smooth", block: "start" });
    window.setTimeout(() => document.getElementById("brief-idea")?.focus(), 350);
  };

  const applyTemplate = (template: (typeof TEMPLATES)[number]) => {
    setBrief((current) => ({
      ...current,
      idea: template.idea,
      style: template.style,
      shot_count: template.shot_count,
      duration_s: template.duration_s,
    }));
    window.setTimeout(() => document.getElementById("brief-idea")?.focus(), 50);
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (creating || brief.idea.trim().length < 2) {
      return;
    }
    setCreating(true);
    try {
      const payload: PromptBrief = {
        title: brief.title.trim(),
        idea: brief.idea.trim(),
        target_model: brief.target_model,
        language: brief.language,
        duration_s: brief.duration_s,
        aspect_ratio: brief.aspect_ratio,
        shot_count: brief.shot_count,
        style: brief.style,
        mood: brief.mood,
        audience: "",
        negative_prompt: brief.negative_prompt,
        constraints: [],
        reference_project_id: brief.reference_project_id || null,
        reference_mode: brief.reference_mode,
      };
      const created = await createPromptProject(payload);
      setBrief((current) => ({ ...current, title: "", idea: "" }));
      selectProject(created.prompt_project_id);
      projectsQuery.refresh();
      showToast("提示词任务已创建，完成后会自动显示结果", "success");
    } catch (error) {
      showToast(error instanceof Error ? error.message : "创建失败", "error");
    } finally {
      setCreating(false);
    }
  };

  const projects = projectsQuery.data ?? [];
  const doneCount = projects.filter((project) => project.status === "done").length;
  const referenceProject = (reverseQuery.data ?? []).find((item) => item.id === brief.reference_project_id);
  const canSubmit = brief.idea.trim().length >= 2 && !creating;
  const stepTwoDone = Boolean(selected && selected.status === "done");

  return (
    <div className="rr-page rr-generate-page">
      <header className="rr-page-heading">
        <div>
          <p className="rr-eyebrow">PROMPT STUDIO / NEW PROJECT</p>
          <h1>把想法，变成可拍的分镜。</h1>
          <p>描述你要拍的片子。系统会沿用参考项目的节奏、画面与镜头语言，生成可直接使用的提示词。</p>
        </div>
        <button className="rr-btn rr-btn-secondary" type="button" onClick={focusBrief}>
          <Icon name="plus" size={15} /> 新建方案
        </button>
      </header>

      <nav className="rr-stepper" aria-label="生成步骤">
        <div className={`rr-stepper-item${brief.idea.trim().length >= 2 ? " is-done" : " is-active"}`}><b>01</b><span><strong>创意 Brief</strong><small>说清楚你要拍什么</small></span></div>
        <div className={`rr-stepper-item${stepTwoDone ? " is-done" : brief.idea.trim().length >= 2 ? " is-active" : ""}`}><b>02</b><span><strong>生成分镜</strong><small>沿用参考结构</small></span></div>
        <div className={`rr-stepper-item${stepTwoDone ? " is-active" : ""}`}><b>03</b><span><strong>导出方案</strong><small>复制或下载提示词</small></span></div>
      </nav>

      <div className="rr-prompt-layout">
        <div className="rr-prompt-main">
          <form className="rr-card rr-brief-card" id="brief-form" onSubmit={submit}>
            <div className="rr-card-head rr-brief-head">
              <div><p className="rr-eyebrow">BRIEF</p><h2>先描述这次的创作目标</h2></div>
              <span className="rr-form-note">{doneCount} 个方案已完成</span>
            </div>

            <div className="rr-template-chips" aria-label="快速模板">
              {TEMPLATES.map((template) => (
                <button key={template.label} className="rr-chip" type="button" onClick={() => applyTemplate(template)}>{template.label}</button>
              ))}
            </div>

            <label className="rr-field-block">
              <span className="rr-field-label">创作描述 <small>写 2–3 句就够</small></span>
              <textarea
                className="rr-input rr-brief-idea"
                id="brief-idea"
                required
                minLength={2}
                maxLength={2000}
                value={brief.idea}
                placeholder="例如：为一家精品咖啡品牌拍 15 秒产品短片，突出手冲过程的专注感与咖啡豆的质感。画面克制、温暖，有真实的环境声，最后落在品牌标识上。"
                onChange={(event) => setBrief({ ...brief, idea: event.target.value })}
              />
            </label>

            <div className="rr-form-grid">
              <label className="rr-field-block">
                <span className="rr-field-label">方案名称 <small>可选</small></span>
                <input className="rr-input" value={brief.title} maxLength={200} placeholder="例如：春日咖啡品牌短片" onChange={(event) => setBrief({ ...brief, title: event.target.value })} />
              </label>
              <label className="rr-field-block">
                <span className="rr-field-label">画面风格 <small>可选</small></span>
                <input className="rr-input" value={brief.style} maxLength={500} placeholder="暖色自然光、胶片颗粒、轻微手持" onChange={(event) => setBrief({ ...brief, style: event.target.value })} />
              </label>
            </div>

            <div className="rr-settings-row" aria-label="生成参数">
              <label className="rr-field-block">
                <span className="rr-field-label">目标模型</span>
                <select className="rr-input" value={brief.target_model} onChange={(event) => setBrief({ ...brief, target_model: event.target.value })}>
                  {TARGET_MODELS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                </select>
              </label>
              <label className="rr-field-block">
                <span className="rr-field-label">画面比例</span>
                <select className="rr-input" value={brief.aspect_ratio} onChange={(event) => setBrief({ ...brief, aspect_ratio: event.target.value })}>
                  {ASPECT_RATIOS.map((ratio) => <option key={ratio} value={ratio}>{ratio}</option>)}
                </select>
              </label>
              <label className="rr-field-block">
                <span className="rr-field-label">镜头数</span>
                <input className="rr-input" type="number" min={1} max={8} value={brief.shot_count} onChange={(event) => setBrief({ ...brief, shot_count: Number(event.target.value) })} />
              </label>
              <label className="rr-field-block">
                <span className="rr-field-label">总时长（秒）</span>
                <input className="rr-input" type="number" min={3} max={120} value={brief.duration_s} onChange={(event) => setBrief({ ...brief, duration_s: Number(event.target.value) })} />
              </label>
            </div>

            <details className="rr-advanced-settings">
              <summary>更多设置 <Icon name="chevron-down" size={15} /></summary>
              <div className="rr-advanced-body">
                <label className="rr-field-block">
                  <span className="rr-field-label">参考逆向项目 <small>可选</small></span>
                  <select className="rr-input" value={brief.reference_project_id} onChange={(event) => setBrief({ ...brief, reference_project_id: event.target.value })}>
                    <option value="">不关联</option>
                    {(reverseQuery.data ?? []).filter((item) => item.status === "done").map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
                  </select>
                </label>
                {brief.reference_project_id ? (
                  <label className="rr-field-block">
                    <span className="rr-field-label">继承方式</span>
                    <select className="rr-input" value={brief.reference_mode} onChange={(event) => setBrief({ ...brief, reference_mode: event.target.value as "style" | "structure" | "full" })}>
                      <option value="style">继承视觉风格</option>
                      <option value="structure">继承镜头结构</option>
                      <option value="full">逐镜参考</option>
                    </select>
                  </label>
                ) : null}
                <label className="rr-field-block">
                  <span className="rr-field-label">语言</span>
                  <select className="rr-input" value={brief.language} onChange={(event) => setBrief({ ...brief, language: event.target.value as "zh" | "en" })}>
                    <option value="zh">中文提示词</option>
                    <option value="en">English prompts</option>
                  </select>
                </label>
                <label className="rr-field-block">
                  <span className="rr-field-label">情绪关键词</span>
                  <input className="rr-input" value={brief.mood} maxLength={200} placeholder="安静、克制、有希望" onChange={(event) => setBrief({ ...brief, mood: event.target.value })} />
                </label>
                <label className="rr-field-block">
                  <span className="rr-field-label">负向提示词</span>
                  <input className="rr-input" value={brief.negative_prompt} maxLength={1000} placeholder="不要出现文字、水印、过曝高光" onChange={(event) => setBrief({ ...brief, negative_prompt: event.target.value })} />
                </label>
              </div>
            </details>
          </form>

          <PromptLibrary
            projects={projects}
            selectedId={selectedId}
            loading={projectsQuery.loading}
            onSelect={selectProject}
            onCreate={focusBrief}
          />
        </div>

        <aside className="rr-prompt-side">
          <section className="rr-card rr-plan-summary-panel" aria-labelledby="summary-panel-title">
            <p className="rr-eyebrow">PLAN SUMMARY</p>
            <h2 id="summary-panel-title">这次要生成什么</h2>
            {referenceProject ? (
              <div className="rr-summary-project">
                <span className="rr-summary-poster"><Icon name="film" size={19} /></span>
                <span><strong>{referenceProject.title}</strong><small>参考项目 · {referenceProject.shot_count} 个镜头</small></span>
              </div>
            ) : null}
            <div className="rr-summary-specs">
              <div><span>目标模型</span><strong>{TARGET_MODELS.find((item) => item.value === brief.target_model)?.label ?? brief.target_model}</strong></div>
              <div><span>画面比例</span><strong>{brief.aspect_ratio}</strong></div>
              <div><span>镜头数</span><strong>{brief.shot_count} 个</strong></div>
              <div><span>总时长</span><strong>{brief.duration_s} 秒</strong></div>
              <div><span>提示词语言</span><strong>{brief.language === "zh" ? "中文" : "English"}</strong></div>
            </div>
            <div className="rr-summary-total"><span>预计生成</span><strong>{brief.shot_count} 个镜头提示词</strong></div>
            <button className="rr-btn rr-btn-primary rr-summary-generate" type="submit" form="brief-form" disabled={!canSubmit}>
              <Icon name={creating ? "refresh" : "sparkles"} size={17} className={creating ? "is-spinning" : ""} />
              {creating ? "正在提交…" : "生成提示词方案"}
            </button>
            <p className="rr-assurance"><Icon name="check" size={13} /> 生成后可逐镜复制、导出或继续生成视频</p>
          </section>
        </aside>
      </div>

      <div className="rr-results-zone">
        {selected ? (
          <PromptDetail key={selected.id} project={selected} />
        ) : detailQuery.loading && selectedId ? (
          <section className="rr-card rr-message-card"><div className="rr-inline-empty"><Icon name="refresh" size={26} className="is-spinning" /><strong>正在读取方案</strong><p>稍候即可查看分镜提示词。</p></div></section>
        ) : (
          <section className="rr-card rr-start-empty">
            <span className="rr-empty-icon"><Icon name="sparkles" size={30} /></span>
            <div><p className="rr-eyebrow">START HERE</p><h2>从一个清晰的想法开始</h2><p>填好上方的创意 Brief，方案会出现在这里。你也可以直接生成视频，或导出 Markdown 交给制作团队。</p></div>
          </section>
        )}
      </div>
    </div>
  );
}
