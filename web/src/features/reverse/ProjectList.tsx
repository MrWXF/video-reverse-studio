import type { ProjectSummary } from "../../api/types";
import { STATUS_LABELS } from "../../utils/format";

interface ProjectListProps {
  projects: ProjectSummary[];
  activeId: string | undefined;
  loading: boolean;
  error: string | null;
  onSelect: (projectId: string) => void;
  onRefresh: () => void;
}

export function ProjectList({ projects, activeId, loading, error, onSelect, onRefresh }: ProjectListProps) {
  return (
    <section className="panel projects-panel" id="projects-panel">
      <div className="panel-head">
        <div>
          <p className="panel-kicker">RECENT PROJECTS</p>
          <h2>视频项目</h2>
        </div>
        <div className="panel-actions">
          <span className="count-badge">{String(projects.length).padStart(2, "0")}</span>
          <button className="btn btn-ghost" type="button" onClick={onRefresh} disabled={loading}>
            {loading ? "刷新中" : "刷新"}
          </button>
        </div>
      </div>
      <div className="project-list">
        {error ? (
          <div className="panel-empty"><span aria-hidden="true">!</span><p>{error}</p></div>
        ) : projects.length === 0 ? (
          <div className="panel-empty"><span aria-hidden="true">◧</span><p>还没有项目</p></div>
        ) : (
          projects.map((project, index) => {
            const running = project.status === "queued" || project.status === "running";
            const progress = Math.round((project.job?.progress ?? 0) * 100);
            const duration = project.duration ? `${project.duration.toFixed(1)}s` : "—";
            return (
              <button
                className={`project-item${project.id === activeId ? " is-selected" : ""}`}
                type="button"
                key={project.id}
                data-status={project.status}
                aria-label={`打开项目 ${project.title}`}
                onClick={() => onSelect(project.id)}
              >
                <span className={`project-thumb tone-project-${(index % 4) + 1}`} aria-hidden="true" />
                <span className="project-copy">
                  <strong>{project.title}</strong>
                  <small>{duration} · {STATUS_LABELS[project.status] ?? project.status}</small>
                </span>
                <i aria-hidden="true">↗</i>
                {running ? <span className="progress-line"><i style={{ width: `${progress}%` }} /></span> : null}
              </button>
            );
          })
        )}
      </div>
    </section>
  );
}
