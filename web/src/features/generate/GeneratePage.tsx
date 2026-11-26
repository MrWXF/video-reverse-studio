import { Link } from "react-router-dom";

export function GeneratePage() {
  return (
    <section className="quality-page">
      <header className="quality-hero">
        <div className="quality-hero-copy">
          <p className="eyebrow">PROMPT GENERATION / 02</p>
          <h1>
            从一个想法，<br />
            <span className="gradient-text">长成完整分镜。</span>
          </h1>
          <p className="hero-description">
            提示词工作区尚未迁移。当前阶段先建立稳定工程和质量页，随后接管 Brief、镜头编辑、版本对比、分享与导出。
          </p>
          <div className="hero-actions">
            <Link className="btn btn-primary" to="/quality">查看迁移进度 <span className="arrow" aria-hidden="true">→</span></Link>
            <a className="btn btn-secondary" href="/">打开经典生成界面</a>
          </div>
        </div>
        <aside className="quality-hero-card">
          <p className="panel-kicker">MIGRATION STATUS</p>
          <strong>04 / 05</strong>
          <p>提示词工作区是功能最密集的阶段，安排在设计、逆向和时间轴之后。</p>
          <div className="quality-live"><i aria-hidden="true" /><span>PLANNED</span></div>
        </aside>
      </header>
    </section>
  );
}
