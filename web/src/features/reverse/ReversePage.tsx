import { useNavigate, useParams } from "react-router-dom";

import { fetchProjects } from "../../api/endpoints";
import { Icon } from "../../components/Icon";
import { StatusBadge } from "../../components/StatusBadge";
import { useApiQuery } from "../../hooks/useApiQuery";
import { formatClock } from "../../utils/format";
import { ProjectDetail } from "./ProjectDetail";
import { ProjectList } from "./ProjectList";
import { UploadPanel } from "./UploadPanel";

function overviewStats(projects: Array<{ status: string; shot_count: number }>) {
  return {
    total: projects.length,
    done: projects.filter((project) => project.status === "done").length,
    active: projects.filter((project) => project.status === "queued" || project.status === "running").length,
    shots: projects.reduce((sum, project) => sum + project.shot_count, 0),
  };
}

export function ReversePage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const projectsQuery = useApiQuery((signal) => fetchProjects(signal), []);
  const projects = projectsQuery.data ?? [];
  const stats = overviewStats(projects);
  const latest = projects[0];

  const focusUpload = () => {
    const target = document.getElementById("create");
    target?.scrollIntoView({ behavior: "smooth", block: "start" });
    window.setTimeout(() => document.getElementById("upload-video-input")?.focus(), 350);
  };

  if (projectId) {
    return (
      <div className="rr-page rr-detail-page">
        <ProjectDetail key={projectId} projectId={projectId} onChanged={projectsQuery.refresh} />
      </div>
    );
  }

  return (
    <div className="rr-page rr-home-page">
      <section className="rr-hero" aria-labelledby="home-title">
        <div className="rr-hero-copy">
          <p className="rr-eyebrow">NEW ANALYSIS / 01</p>
          <h1 id="home-title">上传参考视频，<br /><em>剩下的交给 AI。</em></h1>
          <p>从镜头、节奏到提示词，一次拆解成可复用的创作方案。你只需要选好参考片。</p>
        </div>
        <div className="rr-hero-stats" aria-label="项目概览">
          <div><strong>{String(stats.active).padStart(2, "0")}</strong><span>进行中的项目</span></div>
          <div><strong>{String(stats.shots).padStart(2, "0")}</strong><span>已拆解镜头</span></div>
          <div><strong>{String(stats.done).padStart(2, "0")}</strong><span>已完成分析</span></div>
        </div>
      </section>

      <div className="rr-home-grid">
        <UploadPanel onCreated={(id) => { projectsQuery.refresh(); navigate(`/reverse/${id}`); }} />

        <aside className="rr-home-side">
          {latest ? (
            <section className="rr-card rr-continue-card" aria-labelledby="continue-title">
              <div className="rr-card-head">
                <div><p className="rr-eyebrow">CONTINUE</p><h2 id="continue-title">继续上次</h2></div>
                <StatusBadge status={latest.status} />
              </div>
              <button className="rr-continue-project" type="button" onClick={() => navigate(`/reverse/${latest.id}`)}>
                <span className="rr-continue-thumb">
                  <Icon name="film" size={24} />
                  {latest.duration ? <b>{formatClock(latest.duration)}</b> : null}
                </span>
                <span className="rr-continue-copy">
                  <strong>{latest.title}</strong>
                  <small>{latest.shot_count} 个镜头{latest.duration ? ` · ${latest.duration.toFixed(1)} 秒` : ""}</small>
                </span>
                <Icon name="arrow-right" size={16} />
              </button>
            </section>
          ) : null}

          <ProjectList
            projects={projects}
            activeId={undefined}
            loading={projectsQuery.loading}
            error={projectsQuery.error}
            onSelect={(id) => navigate(`/reverse/${id}`)}
            onRefresh={projectsQuery.refresh}
            onStart={focusUpload}
          />

          <section className="rr-process-strip" aria-label="使用流程">
            <div><span>01</span><strong>上传视频</strong></div>
            <i aria-hidden="true" />
            <div><span>02</span><strong>AI 拆解</strong></div>
            <i aria-hidden="true" />
            <div><span>03</span><strong>生成方案</strong></div>
          </section>
        </aside>
      </div>
    </div>
  );
}
