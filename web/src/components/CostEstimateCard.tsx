import type { CostEstimate } from "../api/types";
import { compactNumber, formatCost, formatNumber } from "../utils/format";

export function CostEstimateCard({ estimate, loading }: { estimate: CostEstimate | null; loading: boolean }) {
  if (loading) {
    return <p className="cost-estimate-note">正在读取视频时长并估算…</p>;
  }
  if (!estimate) {
    return <p className="cost-estimate-note">选择视频后显示预估。</p>;
  }

  const cost = estimate.cost;
  const source = estimate.shot_count_source === "manual" ? "手动镜头数" : "按时长估算";
  return (
    <>
      <div className="cost-estimate-metrics">
        <div>
          <span>SHOTS</span>
          <strong>{formatNumber(estimate.estimated_shots, 0)}</strong>
          <small>{source}</small>
        </div>
        <div>
          <span>TOKENS</span>
          <strong>{compactNumber((cost.prompt_tokens ?? 0) + (cost.completion_tokens ?? 0))}</strong>
          <small>input + output</small>
        </div>
        <div className="is-cost">
          <span>EST. COST</span>
          <strong>{formatCost(cost)}</strong>
          <small>{cost.priced ? "配置单价估算" : "等待配置单价"}</small>
        </div>
      </div>
      <p className="cost-estimate-note">{cost.note || ""}</p>
      {estimate.suggestions.length > 0 ? (
        <ul className="cost-estimate-suggestions">
          {estimate.suggestions.slice(0, 5).map((item) => <li key={item}>{item}</li>)}
        </ul>
      ) : null}
    </>
  );
}
