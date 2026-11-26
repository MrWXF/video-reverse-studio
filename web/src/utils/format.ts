import type { JobStatus, UsageCost } from "../api/types";

export const STATUS_LABELS: Record<JobStatus, string> = {
  uploaded: "待分析",
  queued: "排队中",
  running: "分析中",
  done: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

export const ORIGIN_LABELS: Record<string, string> = {
  filmed: "实拍",
  ai_generated: "AI 生成",
  code_generated: "代码生成",
  unknown: "未知",
};

export function formatNumber(value: number | null | undefined, digits = 1): string {
  const number = Number(value ?? 0);
  return Number.isFinite(number) ? number.toFixed(digits) : "0.0";
}

export function formatClock(value: number | null | undefined): string {
  const total = Math.max(0, Number(value ?? 0));
  const minutes = Math.floor(total / 60);
  const seconds = total - minutes * 60;
  return `${String(minutes).padStart(2, "0")}:${seconds.toFixed(1).padStart(4, "0")}`;
}

export function compactNumber(value: number | null | undefined): string {
  const number = Number(value ?? 0);
  if (number >= 1_000_000) {
    return `${(number / 1_000_000).toFixed(1)}M`;
  }
  if (number >= 1_000) {
    return `${(number / 1_000).toFixed(1)}K`;
  }
  return formatNumber(number, 0);
}

export function formatCost(cost: UsageCost | null | undefined): string {
  if (!cost?.priced || cost.estimated_cost === null || cost.estimated_cost === undefined) {
    return "未配置单价";
  }
  const value = Number(cost.estimated_cost);
  const digits = value > 0 && value < 0.01 ? 6 : 4;
  return `${cost.currency || "USD"} ${value.toFixed(digits)}`;
}
