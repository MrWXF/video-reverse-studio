import { Link } from "react-router-dom";

import { fetchQuality } from "../../api/endpoints";
import type { QualityDashboard, QualityField, QualityTrendPoint } from "../../api/types";
import { PageHeader } from "../../components/PageHeader";
import { useApiQuery } from "../../hooks/useApiQuery";

function formatPercent(value: number | null): string {
  if (value === null || !Number.isFinite(value)) {
    return "暂无";
  }
  return `${(value * 100).toFixed(1)}%`;
}

function formatDuration(value: number | null): string {
  if (value === null || !Number.isFinite(value)) {
    return "—";
  }
  if (value < 60) {
    return `${value.toFixed(1)}s`;
  }
  const minutes = Math.floor(value / 60);
  return `${minutes}m ${Math.round(value - minutes * 60)}s`;
}

function compactNumber(value: number): string {
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1)}M`;
  }
  if (value >= 1_000) {
    return `${(value / 1_000).toFixed(1)}K`;
  }
  return String(value);
}

function KpiCard({ label, value, detail, tone }: { label: string; value: string; detail: string; tone?: string }) {
  return (
    <article className={`quality-kpi ${tone ?? ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function Kpis({ data }: { data: QualityDashboard }) {
  const summary = data.summary;
  return (
    <section className="quality-kpis" aria-live="polite">
      <KpiCard
        label="来源判定准确率"
        value={formatPercent(summary.origin_accuracy)}
        detail={`${summary.origin_corrections} 镜发生来源修正 · 基于人工编辑`}
        tone={summary.origin_accuracy === null ? undefined : summary.origin_accuracy < 0.85 ? "is-warning" : "is-good"}
      />
      <KpiCard
        label="镜头修正率"
        value={formatPercent(summary.correction_rate)}
        detail={`${summary.edited_shots} / ${summary.shots} 镜被人工修改`}
        tone={summary.correction_rate !== null && summary.correction_rate > 0.3 ? "is-warning" : undefined}
      />
      <KpiCard
        label="平均处理时长"
        value={formatDuration(summary.average_processing_seconds)}
        detail={`${summary.analysis_runs} 次完成分析`}
      />
      <KpiCard
        label="TOKEN 消耗"
        value={compactNumber(summary.total_tokens)}
        detail={`${summary.total_calls} 次模型调用 · input + output`}
      />
    </section>
  );
}

function Fields({ fields }: { fields: QualityField[] }) {
  const total = fields.reduce((sum, item) => sum + item.count, 0);
  const maximum = Math.max(...fields.map((item) => item.count), 1);

  return (
    <article className="panel quality-panel">
      <div className="quality-panel-head">
        <div>
          <p className="panel-kicker">FIELD SIGNALS</p>
          <h2>字段修正频率</h2>
        </div>
        <span className="count-badge">{total} 次</span>
      </div>
      <div className="quality-fields-body">
        {fields.length === 0 ? (
          <p className="quality-empty">还没有字段修正记录。编辑镜头后，这里会显示最容易出错的字段。</p>
        ) : (
          fields.map((field) => (
            <div className="quality-field-row" key={field.field}>
              <div className="quality-field-copy">
                <strong>{field.label}</strong>
                <span>
                  {field.count} 次 · {field.affected_shots} 镜 · 修正率 {formatPercent(field.rate)}
                </span>
              </div>
              <div className="quality-field-bar" aria-hidden="true">
                <i style={{ width: `${Math.max(3, (field.count / maximum) * 100).toFixed(1)}%` }} />
              </div>
            </div>
          ))
        )}
      </div>
    </article>
  );
}

function Trend({ points }: { points: QualityTrendPoint[] }) {
  const maximum = Math.max(...points.map((point) => point.field_corrections), 1);
  const labelStep = Math.max(1, Math.ceil(points.length / 7));
  return (
    <article className="panel quality-panel">
      <div className="quality-panel-head">
        <div>
          <p className="panel-kicker">EDIT TREND</p>
          <h2>近 30 天修正趋势</h2>
        </div>
        <span className="quality-legend"><i />来源修正</span>
      </div>
      <div className="quality-trend-body">
        {points.length === 0 ? (
          <p className="quality-empty">时间窗口内没有趋势数据。</p>
        ) : (
          <>
            <div className="quality-trend-chart" style={{ "--trend-cols": points.length } as React.CSSProperties}>
              {points.map((point, index) => {
                const height = point.field_corrections ? Math.max(4, (point.field_corrections / maximum) * 100) : 0;
                const originHeight = point.field_corrections
                  ? Math.max(0, (point.origin_corrections / point.field_corrections) * 100)
                  : 0;
                const showLabel = index % labelStep === 0 || index === points.length - 1;
                return (
                  <div
                    className="quality-trend-column"
                    key={point.date}
                    title={`${point.date} · ${point.field_corrections} 个字段修正 · ${point.edit_events} 次编辑`}
                  >
                    <span className="quality-trend-bar" style={{ height: `${height.toFixed(1)}%` }}>
                      <i style={{ height: `${originHeight.toFixed(1)}%` }} />
                    </span>
                    <b>{showLabel ? point.date.slice(5) : ""}</b>
                  </div>
                );
              })}
            </div>
            <div className="quality-trend-legend">
              <span><i className="is-total" />字段修正</span>
              <span><i className="is-origin" />来源修正</span>
            </div>
            <p className="quality-trend-note">柱高表示当天字段修正总量，深色部分为来源判定修正。</p>
          </>
        )}
      </div>
    </article>
  );
}

function ProjectRows({ data }: { data: QualityDashboard }) {
  return (
    <article className="panel quality-panel">
      <div className="quality-panel-head">
        <div>
          <p className="panel-kicker">PROJECT BREAKDOWN</p>
          <h2>项目质量明细</h2>
        </div>
      </div>
      <div className="quality-projects-body">
        {data.projects.length === 0 ? (
          <p className="quality-empty">窗口内没有可展示的项目。</p>
        ) : (
          data.projects.map((project) => (
            <div className="quality-project-row" key={project.id}>
              <div className="quality-project-copy">
                <strong>{project.title}</strong>
                <small>{project.shot_count} 镜 · {project.status}</small>
              </div>
              <div className="quality-project-stats">
                <span><b>{project.edit_events}</b> 事件</span>
                <span><b>{project.edited_shots}</b> 修正镜</span>
                <span><b>{project.origin_corrections}</b> 来源</span>
              </div>
              <Link className="btn btn-ghost" to={`/reverse/${project.id}`}>查看项目</Link>
            </div>
          ))
        )}
      </div>
    </article>
  );
}

function Suggestions({ items }: { items: string[] }) {
  return (
    <article className="panel quality-panel quality-suggestions-panel">
      <div className="quality-panel-head">
        <div>
          <p className="panel-kicker">NEXT ACTION</p>
          <h2>系统建议</h2>
        </div>
      </div>
      <div className="quality-suggestions-body">
        {items.length === 0 ? (
          <p className="quality-empty">暂无可展示的建议。</p>
        ) : (
          <ul className="quality-suggestion-list">
            {items.map((item, index) => (
              <li key={item}>
                <b>{String(index + 1).padStart(2, "0")}</b>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </article>
  );
}

export function QualityPage() {
  const query = useApiQuery((signal) => fetchQuality(30, signal), []);
  const data = query.data;

  return (
    <section className="rr-page rr-quality-page">
      <PageHeader
        eyebrow="QUALITY INSIGHT"
        title="用真实修正数据，找到最该优化的环节"
        description="汇总人工修正、处理耗时和 Token 消耗，快速判断哪些镜头字段最需要改进，以及下一轮应该优先处理什么。"
        actions={<>
          <button className="btn btn-primary" type="button" onClick={query.refresh} disabled={query.loading}>
            {query.loading ? "正在刷新…" : "刷新质量数据"}
          </button>
          <Link className="btn btn-secondary" to="/reverse">返回视频分析</Link>
        </>}
      />

      <div className="quality-signal-bar" aria-live="polite">
        <span className="quality-live"><i aria-hidden="true" /><span>EDIT EVENT SIGNAL</span></span>
        <div>
          <strong>{data ? `近 ${data.window.days} 天` : "近 30 天"}</strong>
          <p>
            {data
              ? `${data.summary.projects} 个活跃项目 · ${data.summary.shots} 个镜头 · ${data.summary.edit_events} 次人工修正`
              : query.loading
                ? "正在读取质量数据…"
                : "质量数据暂不可用"}
          </p>
        </div>
      </div>

      {query.error ? (
        <section className="panel react-message-panel">
          <h2>质量数据读取失败</h2>
          <p>{query.error}</p>
          <button className="btn btn-secondary" type="button" onClick={query.refresh}>重试</button>
        </section>
      ) : data ? (
        <>
          <Kpis data={data} />
          <section className="quality-grid">
            <Fields fields={data.fields} />
            <Trend points={data.trend} />
          </section>
          <section className="quality-grid">
            <ProjectRows data={data} />
            <Suggestions items={data.suggestions} />
          </section>
        </>
      ) : (
        <section className="panel react-message-panel" aria-live="polite">
          <h2>正在聚合质量指标</h2>
          <p>读取人工修正、分析耗时和 token 消耗。</p>
        </section>
      )}
    </section>
  );
}
