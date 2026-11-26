export function ReverseHero() {
  return (
    <>
      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">REVERSE ENGINEERING / 01</p>
          <h1>
            把参考视频，<br />
            <span className="gradient-text">
              拆成可复用的<br />创作配方。
            </span>
          </h1>
          <p className="hero-description">
            上传一段喜欢的视频，自动完成镜头切分、关键帧抽取、画面分析与提示词逆向。最后得到的不只是分析报告，而是一份能继续拍摄、继续生成、继续交付的创作底稿。
          </p>
          <div className="hero-actions">
            <a className="btn btn-primary" href="#create">
              上传参考视频 <span className="arrow" aria-hidden="true">↗</span>
            </a>
            <a className="btn btn-secondary" href="#detail">查看项目结果</a>
          </div>
          <div className="trust-row">
            <span>镜头级拆解</span>
            <span>Prompt + Negative</span>
            <span>一键导出 Markdown</span>
          </div>
          <p className="hero-note"><i aria-hidden="true" /> 支持 MP4 / MOV / WEBM · 单条最长 3 分钟</p>
        </div>

        <div className="hero-art" aria-hidden="true">
          <article className="art-stage">
            <div className="art-window">
              <div className="art-window-top">
                <span className="art-window-label">REVERSE PREVIEW / 01</span>
                <span className="art-live">ANALYZING</span>
              </div>
              <div className="art-visual">
                <span className="art-sun" />
                <span className="art-horizon" />
                <span className="art-grain" />
                <span className="art-focus"><b>SUBJECT / 01</b><i>03.8s</i></span>
                <div className="art-timeline"><i /><i /><i /><i /><b>00:15 / 00:15</b></div>
              </div>
              <div className="art-window-bottom">
                <div className="art-caption">
                  <strong>镜头语言 · 15s</strong>
                  <span>9:16 · 24 FPS · 4 SHOTS</span>
                </div>
                <div className="art-wave"><i /><i /><i /><i /><i /><i /></div>
              </div>
            </div>
          </article>
          <div className="float-card float-a"><span>VISION ENGINE</span><strong>6 维镜头理解</strong></div>
          <div className="float-card float-b"><span>REUSABLE RECIPE</span><strong>Prompt · Light · Pace</strong></div>
        </div>
      </section>

      <section className="stat-strip" aria-label="能力概览">
        <div className="stat"><strong>06 <span>维</span></strong><p>景别、运镜、光线、构图、节奏与色彩</p><em>VISION</em></div>
        <div className="stat"><strong>24 <span>镜</span></strong><p>单条视频最多拆解 24 个独立镜头</p><em>SHOTS</em></div>
        <div className="stat"><strong>02 <span>格式</span></strong><p>Markdown 创作底稿与 JSON 结构化数据</p><em>EXPORT</em></div>
        <div className="stat"><strong>98<span>%</span></strong><p>镜头语言分析平均可用度</p><em>QUALITY</em></div>
      </section>
    </>
  );
}
