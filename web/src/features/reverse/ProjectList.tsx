import { useMemo, useState } from "react";

import type { ProjectSummary } from "../../api/types";
import { Icon } from "../../components/Icon";
import { StatusBadge } from "../../components/StatusBadge";
import { formatClock } from "../../utils/format";

type ProjectFilter = "all" | "active" | "done" | "attention";

interface ProjectListProps {
  projects: ProjectSummary[];
  activeId: string | undefined;
  loading: boolean;
  error: string | null;
  onSelect: (projectId: string) => void;
  onRefresh: () => void;
  onStart?: () => void;
}

function dateLabel(value: string | null): string {
  if (!value) {
    return "刚刚";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  const elapsed = Date.now() - date.getTime();
  const minutes = Math.floor(elapsed / 60000);
  if (minutes < 1) {
    return "刚刚";
  }
  if (minutes < 60) {
    return `${minutes} 分钟前`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours} 小时前`;
  }
  return date.toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" });
}

function matchesFilter(project: ProjectSummary, filter: ProjectFilter): boolean {
  if (filter === "active") {
    return project.status === "queued" || project.status === "running";
  }
  if (filter === "done") {
    return project.status === "done";
  }
  if (filter === "attention") {
    return project.status === "failed" || project.status === "cancelled";
  }
  return true;
}

export function ProjectList({ projects, activeId, loading, error, onSelect, onRefresh, onStart }: ProjectListProps) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<ProjectFilter>("all");
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return projects.filter((project) => (
      matchesFilter(project, filter)
      && (!needle || project.title.toLowerCase().includes(needle))
    ));
  }, [filter, projects, query]);

  const counts = useMemo(() => ({
    all: projects.length,
    active: projects.filter((project) => matchesFilter(project, "active")).length,
    done: projects.filter((project) => matchesFilter(project, "done")).length,
    attention: projects.filter((project) => matchesFilter(project, "attention")).length,
  }), [projects]);

  return (
    <section className="rr-card rr-project-browser" id="projects-panel" aria-labelledby="projects-title">
      <div className="rr-card-head">
        <div><p className="rr-eyebrow">PROJECT LIBRARY</p><h2 id="projects-title">最近项目</h2></div>
        <div className="rr-card-actions">
          <span className="rr-count-badge">{String(projects.length).padStart(2, "0")}</span>
          <button className="rr-icon-btn" type="button" onClick={onRefresh} disabled={loading} aria-label="刷新项目列表">
            <Icon name="refresh" size={16} className={loading ? "is-spinning" : ""} />
          </button>
          {onStart ? <button className="rr-icon-btn is-accent" type="button" onClick={onStart} aria-label="新建视频分析"><Icon name="plus" size={17} /></button> : null}
        </div>
      </div>

      <div className="rr-project-tools">
        <label className="rr-search-field">
          <Icon name="search" size={16} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索项目" aria-label="搜索项目" />
        </label>
        <div className="rr-filter-chips" role="group" aria-label="按状态筛选项目">
          {([
            ["all", "全部"],
            ["active", "进行中"],
            ["done", "已完成"],
            ["attention", "需处理"],
          ] as const).map(([value, label]) => (
            <button key={value} type="button" className={filter === value ? "is-active" : ""} aria-pressed={filter === value} onClick={() => setFilter(value)}>
              {label}<span>{counts[value]}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="rr-gallery">
        {error ? (
          <div className="rr-inline-empty is-error"><Icon name="alert" size={20} /><p>{error}</p><button className="rr-btn rr-btn-ghost" type="button" onClick={onRefresh}>重试</button></div>
        ) : filtered.length === 0 ? (
          <div className="rr-inline-empty">
            <Icon name={projects.length ? "search" : "folder"} size={24} />
            <strong>{projects.length ? "没有匹配的项目" : "还没有视频分析"}</strong>
            <p>{projects.length ? "换个关键词或筛选条件试试。" : "上传第一段参考视频，开始拆解镜头语言。"}</p>
            {onStart && !projects.length ? <button className="rr-btn rr-btn-secondary" type="button" onClick={onStart}><Icon name="upload" size={15} /> 上传视频</button> : null}
          </div>
        ) : filtered.map((project) => {
          const running = project.status === "queued" || project.status === "running";
          const progress = Math.round((project.job?.progress ?? 0) * 100);
          const duration = project.duration ? `${project.duration.toFixed(1)} 秒` : "时长待读取";
          return (
            <button
              className={`rr-gallery-card${project.id === activeId ? " is-selected" : ""}`}
              type="button"
              key={project.id}
              data-status={project.status}
              aria-label={`打开项目 ${project.title}`}
              onClick={() => onSelect(project.id)}
            >
              <span className="rr-gallery-thumb">
                <Icon name="film" size={26} />
                <span className="rr-gallery-tag"><StatusBadge status={project.status} /></span>
                {project.duration ? <b>{formatClock(project.duration)}</b> : null}
              </span>
              <span className="rr-gallery-meta">
                <strong>{project.title}</strong>
                <small>{project.shot_count} 个镜头 · {duration} · {dateLabel(project.created_at)}</small>
                {running ? (
                  <span className="rr-project-progress"><i style={{ width: `${progress}%` }} /><small>{progress}%</small></span>
                ) : null}
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
