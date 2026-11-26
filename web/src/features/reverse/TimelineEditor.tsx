import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";

import {
  mergeTimelineShots,
  reanalyzeTimelineShot,
  splitTimelineShot,
  updateTimelineBoundary,
} from "../../api/endpoints";
import type { ProjectDetail, Shot, TimelineMutation } from "../../api/types";
import { useUiStore } from "../../store/uiStore";
import { formatClock } from "../../utils/format";

interface DragState {
  pointerId: number;
  leftId: number;
  rightId: number;
  lower: number;
  upper: number;
  original: number;
  boundary: number;
}

interface TimelineEditorProps {
  project: ProjectDetail;
  running: boolean;
  onMutated: () => void;
  onSeek?: (seconds: number) => void;
}

function roundTimelineValue(value: number): number {
  return Math.round(Number(value || 0) * 1000) / 1000;
}

function minimumDuration(project: ProjectDetail): number {
  const value = Number(project.timeline_min_shot_seconds);
  return Number.isFinite(value) && value > 0 ? value : 0.8;
}

function timelineTotal(project: ProjectDetail, shots: Shot[]): number {
  const lastEnd = shots.length ? Number(shots[shots.length - 1].end_s || 0) : 0;
  return Math.max(Number(project.duration || 0), lastEnd, 0.1);
}

function splitPointOf(shot: Shot, minimum: number): number | null {
  const lower = roundTimelineValue(Number(shot.start_s) + minimum);
  const upper = roundTimelineValue(Number(shot.end_s) - minimum);
  if (lower > upper) {
    return null;
  }
  const midpoint = roundTimelineValue((Number(shot.start_s) + Number(shot.end_s)) / 2);
  return Math.min(upper, Math.max(lower, midpoint));
}

function splitValue(value: number | null): string {
  if (value === null) {
    return "";
  }
  return value.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
}

function clamp(value: number, lower: number, upper: number): number {
  return Math.min(upper, Math.max(lower, value));
}

export function TimelineEditor({ project, running, onMutated, onSeek }: TimelineEditorProps) {
  const shots = project.shots;
  const minimum = minimumDuration(project);
  const total = timelineTotal(project, shots);
  const showToast = useUiStore((state) => state.showToast);
  const trackRef = useRef<HTMLDivElement>(null);
  const [selectedShotId, setSelectedShotId] = useState<number | null>(shots[0]?.id ?? null);
  const [splitAt, setSplitAt] = useState("");
  const [drag, setDrag] = useState<DragState | null>(null);
  const [busy, setBusy] = useState(false);
  const locked = running || busy;

  const selectedShot = shots.find((shot) => shot.id === selectedShotId) ?? shots[0];
  const selectedPosition = selectedShot ? shots.findIndex((shot) => shot.id === selectedShot.id) : -1;
  const selectedSplitPoint = selectedShot ? splitPointOf(selectedShot, minimum) : null;
  const splitLower = selectedShot ? roundTimelineValue(Number(selectedShot.start_s) + minimum) : 0;
  const splitUpper = selectedShot ? roundTimelineValue(Number(selectedShot.end_s) - minimum) : 0;
  const canSplit = selectedSplitPoint !== null;
  const canMerge = selectedPosition >= 0 && selectedPosition < shots.length - 1;

  useEffect(() => {
    if (!shots.length) {
      setSelectedShotId(null);
      return;
    }
    if (!shots.some((shot) => shot.id === selectedShotId)) {
      setSelectedShotId(shots[0].id);
    }
  }, [selectedShotId, shots]);

  useEffect(() => {
    setSplitAt(splitValue(selectedSplitPoint));
  }, [selectedShot?.end_s, selectedShot?.id, selectedShot?.start_s, selectedSplitPoint]);

  useEffect(() => {
    if (!drag) {
      return undefined;
    }
    document.body.classList.add("timeline-dragging");
    return () => document.body.classList.remove("timeline-dragging");
  }, [drag]);

  const selectShot = (shot: Shot) => {
    setSelectedShotId(shot.id);
    onSeek?.(shot.start_s);
  };

  const execute = async (
    operation: () => Promise<TimelineMutation>,
    successMessage: string,
  ): Promise<boolean> => {
    setBusy(true);
    try {
      const result = await operation();
      const warning = result.prompt_projects_invalidated
        ? `；${result.prompt_projects_invalidated} 个提示词方案需要重新校准`
        : "";
      showToast(`${successMessage}${warning}`, "success");
      onMutated();
      return true;
    } catch (error) {
      showToast(error instanceof Error ? error.message : "时间轴操作失败", "error");
      return false;
    } finally {
      setBusy(false);
    }
  };

  const commitBoundary = (left: Shot, boundary: number) => {
    const value = roundTimelineValue(boundary);
    if (Math.abs(value - roundTimelineValue(left.end_s)) < 0.001) {
      return;
    }
    void execute(
      () => updateTimelineBoundary(project.id, left.id, value),
      "边界已调整，正在重新分析相邻镜头",
    );
  };

  const startDrag = (
    event: ReactPointerEvent<HTMLButtonElement>,
    left: Shot,
    right: Shot,
    lower: number,
    upper: number,
  ) => {
    if (event.button !== 0 || locked || lower > upper) {
      return;
    }
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    setSelectedShotId(left.id);
    onSeek?.(left.start_s);
    setDrag({
      pointerId: event.pointerId,
      leftId: left.id,
      rightId: right.id,
      lower,
      upper,
      original: roundTimelineValue(left.end_s),
      boundary: roundTimelineValue(left.end_s),
    });
  };

  const moveDrag = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (!drag || event.pointerId !== drag.pointerId || !trackRef.current) {
      return;
    }
    const rect = trackRef.current.getBoundingClientRect();
    if (!rect.width) {
      return;
    }
    const raw = ((event.clientX - rect.left) / rect.width) * total;
    const boundary = roundTimelineValue(clamp(raw, drag.lower, drag.upper));
    setDrag((current) => (current ? { ...current, boundary } : current));
    event.preventDefault();
  };

  const finishDrag = (
    event: ReactPointerEvent<HTMLButtonElement>,
    cancelled: boolean,
  ) => {
    if (!drag || event.pointerId !== drag.pointerId) {
      return;
    }
    try {
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
    } catch {
      // Pointer capture may already have been released by the browser.
    }
    const changed = Math.abs(drag.boundary - drag.original) >= 0.001;
    const left = shots.find((shot) => shot.id === drag.leftId);
    setDrag(null);
    if (cancelled || !changed || !left) {
      return;
    }
    commitBoundary(left, drag.boundary);
  };

  const nudgeBoundary = (
    event: ReactKeyboardEvent<HTMLButtonElement>,
    left: Shot,
    lower: number,
    upper: number,
  ) => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key) || locked) {
      return;
    }
    event.preventDefault();
    const step = event.shiftKey ? 0.5 : 0.1;
    const delta = event.key === "ArrowRight" ? step : -step;
    const boundary = roundTimelineValue(clamp(Number(left.end_s) + delta, lower, upper));
    commitBoundary(left, boundary);
  };

  const splitSelected = () => {
    if (!selectedShot || locked) {
      return;
    }
    const point = Number(splitAt);
    if (!Number.isFinite(point) || point < splitLower || point > splitUpper) {
      showToast(
        `拆分点必须位于 ${splitLower.toFixed(1)}s 到 ${splitUpper.toFixed(1)}s 之间`,
        "error",
      );
      return;
    }
    void execute(
      () => splitTimelineShot(project.id, selectedShot.id, roundTimelineValue(point)),
      "镜头已拆分，正在重新分析",
    );
  };

  const mergeSelected = () => {
    if (!selectedShot || !canMerge || locked) {
      return;
    }
    const next = shots[selectedPosition + 1];
    void execute(
      () => mergeTimelineShots(project.id, [selectedShot.id, next.id]),
      "镜头已合并，正在重新分析",
    );
  };

  const reanalyzeSelected = () => {
    if (!selectedShot || locked) {
      return;
    }
    void execute(
      () => reanalyzeTimelineShot(project.id, selectedShot.id),
      "已开始重抽关键帧并重新分析",
    );
  };

  if (!shots.length || !selectedShot) {
    return null;
  }

  return (
    <section className={`shot-timeline${locked ? " is-locked" : ""}`} aria-label="镜头时间轴编辑">
      <div className="timeline-head">
        <div>
          <span className="panel-kicker">TIMELINE EDITOR</span>
          <h3>时间轴结构编辑</h3>
        </div>
        <div className="timeline-head-meta">
          <strong>{shots.length}</strong>
          <span>镜头 · {formatClock(total)}</span>
        </div>
      </div>

      <div className="timeline-stage">
        <div ref={trackRef} className={`timeline-track${drag ? " is-dragging" : ""}`}>
          {shots.map((shot, index) => {
            const originalStart = Number(shot.start_s || 0);
            const originalEnd = Number(shot.end_s || originalStart);
            const start = drag?.rightId === shot.id ? drag.boundary : originalStart;
            const end = drag?.leftId === shot.id ? drag.boundary : originalEnd;
            const selected = shot.id === selectedShot.id;
            const subject = shot.analysis?.subject || shot.analysis?.shot_type || "镜头";
            return (
              <button
                key={shot.id}
                className={`timeline-segment tone-${(index % 4) + 1}${selected ? " is-selected" : ""}`}
                type="button"
                data-timeline-shot={shot.id}
                data-shot-start={start}
                style={{
                  left: `${(Math.max(0, start) / total) * 100}%`,
                  width: `${Math.max(0.4, ((Math.max(start, end) - start) / total) * 100)}%`,
                }}
                aria-pressed={selected}
                title={`镜头 ${String(shot.index).padStart(2, "0")} · ${subject}`}
                onClick={() => selectShot(shot)}
              >
                {shot.keyframe_url ? (
                  <img className="timeline-segment-frame" src={shot.keyframe_url} alt="" loading="lazy" />
                ) : null}
                <span className="timeline-segment-shade" />
                <span className="timeline-segment-no">{String(shot.index).padStart(2, "0")}</span>
                <span className="timeline-segment-copy">
                  <strong>{subject}</strong>
                  <small>{formatClock(start)} — {formatClock(end)}</small>
                </span>
              </button>
            );
          })}

          {shots.slice(0, -1).map((left, index) => {
            const right = shots[index + 1];
            const lower = roundTimelineValue(Number(left.start_s) + minimum);
            const upper = roundTimelineValue(Number(right.end_s) - minimum);
            if (lower > upper) {
              return null;
            }
            const boundary = drag?.leftId === left.id ? drag.boundary : roundTimelineValue(left.end_s);
            return (
              <button
                key={`boundary-${left.id}`}
                className={`timeline-handle${drag?.leftId === left.id ? " is-dragging" : ""}`}
                type="button"
                data-timeline-boundary={left.id}
                role="slider"
                aria-label={`调整镜头 ${String(left.index).padStart(2, "0")} 与下一镜的边界`}
                aria-orientation="horizontal"
                aria-valuemin={lower}
                aria-valuemax={upper}
                aria-valuenow={boundary}
                style={{ left: `${(boundary / total) * 100}%` }}
                disabled={locked}
                onPointerDown={(event) => startDrag(event, left, right, lower, upper)}
                onPointerMove={moveDrag}
                onPointerUp={(event) => finishDrag(event, false)}
                onPointerCancel={(event) => finishDrag(event, true)}
                onKeyDown={(event) => nudgeBoundary(event, left, lower, upper)}
              >
                <span className="timeline-handle-time">{formatClock(boundary)}</span>
                <span className="timeline-handle-dot" aria-hidden="true" />
              </button>
            );
          })}
        </div>

        <div className="timeline-scale" aria-hidden="true">
          {[0, 0.25, 0.5, 0.75, 1].map((ratio) => (
            <span key={ratio} style={{ left: `${ratio * 100}%` }}>{formatClock(total * ratio)}</span>
          ))}
        </div>
      </div>

      <div className="timeline-actions" data-selected-shot-id={selectedShot.id}>
        <div className="timeline-selection">
          <span>SELECTED SHOT</span>
          <strong>
            镜头 {String(selectedShot.index).padStart(2, "0")} · {formatClock(selectedShot.start_s)} — {formatClock(selectedShot.end_s)}
          </strong>
          <small>点击镜头定位画面；拖动边界手柄，或聚焦手柄后按 ← → 微调。</small>
        </div>
        <div className="timeline-controls">
          <label className="timeline-split-field">
            <span>拆分点</span>
            <span className="timeline-input-wrap">
              <input
                className="input"
                data-timeline-split-at=""
                type="number"
                step="0.1"
                min={canSplit ? splitLower : undefined}
                max={canSplit ? splitUpper : undefined}
                value={splitAt}
                disabled={locked || !canSplit}
                onChange={(event) => setSplitAt(event.target.value)}
              />
              <em>s</em>
            </span>
          </label>
          <button
            className="btn btn-secondary"
            type="button"
            data-timeline-split=""
            disabled={locked || !canSplit}
            onClick={splitSelected}
          >
            拆分镜头
          </button>
          <button
            className="btn btn-ghost"
            type="button"
            data-timeline-merge=""
            disabled={locked || !canMerge}
            onClick={mergeSelected}
          >
            与下一镜合并
          </button>
          <button
            className="btn btn-ghost"
            type="button"
            data-timeline-reanalyze=""
            disabled={locked}
            onClick={reanalyzeSelected}
          >
            {busy ? "正在提交…" : "重抽帧并重分析"}
          </button>
        </div>
      </div>
      <p className="timeline-range-hint">
        {canSplit
          ? `拆分点 ${splitLower.toFixed(1)}s — ${splitUpper.toFixed(1)}s`
          : "镜头过短，暂不可拆分"}
      </p>
    </section>
  );
}
