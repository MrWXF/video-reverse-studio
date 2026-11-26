import { Link, useNavigate, useParams } from "react-router-dom";

import { fetchProjects } from "../../api/endpoints";
import { useApiQuery } from "../../hooks/useApiQuery";
import { ProjectDetail } from "./ProjectDetail";
import { ProjectList } from "./ProjectList";
import { ReverseHero } from "./ReverseHero";
import { UploadPanel } from "./UploadPanel";

export function ReversePage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const projectsQuery = useApiQuery((signal) => fetchProjects(signal), []);

  return (
    <>
      <ReverseHero />

      <section className="workspace">
        <aside className="workspace-side">
          <UploadPanel onCreated={(id) => { projectsQuery.refresh(); navigate(`/reverse/${id}`); }} />
          <ProjectList
            projects={projectsQuery.data ?? []}
            activeId={projectId}
            loading={projectsQuery.loading}
            error={projectsQuery.error}
            onSelect={(id) => navigate(`/reverse/${id}`)}
            onRefresh={projectsQuery.refresh}
          />
        </aside>

        {projectId ? (
          <ProjectDetail key={projectId} projectId={projectId} onChanged={projectsQuery.refresh} />
        ) : (
          <section className="panel result-panel detail-panel" id="detail">
            <div className="empty">
              <span className="empty-icon" aria-hidden="true">◧</span>
              <h3>等待一个视频</h3>
              <p>上传素材，或从左侧选择一个已有项目。</p>
            </div>
          </section>
        )}
      </section>

      <section className="closing-banner">
        <div>
          <p className="panel-kicker">FROM REFERENCE TO RECIPE</p>
          <h2>最后得到的，不只是一份分析报告。</h2>
          <p>镜头、提示词、节奏与色彩依据都会被保留。团队可以直接审阅，也可以把配方交给下一次生成。</p>
        </div>
        <div className="closing-actions">
          <Link className="btn btn-secondary" to="/generate">继续生成提示词 <span aria-hidden="true">↗</span></Link>
        </div>
      </section>
    </>
  );
}
