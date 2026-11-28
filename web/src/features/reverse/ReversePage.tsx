import { useNavigate, useParams } from "react-router-dom";

import { fetchProjects } from "../../api/endpoints";
import { useApiQuery } from "../../hooks/useApiQuery";
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
          <p className="rr-eyebrow">AI VIDEO REVERSE STUDIO</p>
          <h1 id="home-title">把任意视频，<em>逆向成可复刻的配方</em></h1>
          <p>上传参考片，自动完成分镜检测、关键帧抽取、逐镜分析与提示词生成。</p>
        </div>
        <div className="rr-hero-stats" aria-label="项目概览">
          <div><strong>{String(stats.active).padStart(2, "0")}</strong><span>进行中的项目</span></div>
          <div><strong>{String(stats.shots).padStart(2, "0")}</strong><span>已拆解镜头</span></div>
          <div><strong>{String(stats.done).padStart(2, "0")}</strong><span>已完成分析</span></div>
        </div>
      </section>

      <UploadPanel onCreated={(id) => { projectsQuery.refresh(); navigate(`/reverse/${id}`); }} />

      <section className="rr-process-strip" aria-label="使用流程">
        <div><span>01</span><strong>上传视频</strong></div>
        <i aria-hidden="true" />
        <div><span>02</span><strong>AI 拆解</strong></div>
        <i aria-hidden="true" />
        <div><span>03</span><strong>生成方案</strong></div>
      </section>

      <ProjectList
        projects={projects}
        activeId={undefined}
        loading={projectsQuery.loading}
        error={projectsQuery.error}
        onSelect={(id) => navigate(`/reverse/${id}`)}
        onRefresh={projectsQuery.refresh}
        onStart={focusUpload}
      />
    </div>
  );
}
