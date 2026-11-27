import type { JobStatus } from "../api/types";
import { STATUS_LABELS } from "../utils/format";

export function StatusBadge({
  status,
  label,
}: {
  status: JobStatus | "partial" | "succeeded" | string;
  label?: string;
}) {
  const text = label ?? STATUS_LABELS[status as JobStatus] ?? status;
  return (
    <span className={`ui-status is-${status}`}>
      <i aria-hidden="true" />
      {text}
    </span>
  );
}
