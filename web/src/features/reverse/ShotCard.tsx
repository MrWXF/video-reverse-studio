import { useState } from "react";

import type { ProjectDetail, Shot } from "../../api/types";
import { useUiStore } from "../../store/uiStore";
import { formatClock, ORIGIN_LABELS } from "../../utils/format";

export function ShotCard({ shot, position, project }: { shot: Shot; position: number; project: ProjectDetail }) {
  const [expanded, setExpanded] = useState(position === 0);
  const showToast = useUiStore((state) => state.showToast);
  const analysis = shot.analysis;
  const index = String(shot.index).padStart(2, "0");
  const palette = analysis.color_palette ?? [];
  const tags = [analysis.shot_type, analysis.camera_movement, analysis.lighting, ORIGIN_LABELS[shot.origin] ?? shot.origin]
    .filter((item): item is string => Boolean(item));
  const notes = analysis.remake_notes || (shot.transcript ? `口播：${shot.transcript}` : "暂无补充说明");

  const copyPrompt = async () => {
    if (!analysis.prompt) {
      return;
    }
    try {
      await navigator.clipboard.writeText(analysis.prompt);
      showToast("Prompt 已复制", "success");
    } catch {
      showToast("复制失败，请手动选择文本", "error");
    }
  };

  return (
    <article className={`result-card tone-${(position % 4) + 1}${expanded ? "" : " is-collapsed"}`}>
      <button className="shot-toggle" type="button" aria-expanded={expanded} onClick={() => setExpanded((value) => !value)}>
        <span className="shot-index">{index}</span>
        <span className="shot-visual">
          {shot.keyframe_url ? <img src={shot.keyframe_url} alt={`镜头 ${index} 关键帧`} loading="lazy" /> : <span className="no-frame">无关键帧</span>}
          <b>{formatClock(shot.end_s)}</b>
        </span>
        <span className="shot-info">
          <h4>镜头 {index} · {analysis.subject || analysis.shot_type || "画面分析"}</h4>
          <p>{analysis.scene || analysis.visual_style || "镜头语言与视觉信息"}</p>
          <span className="shot-tags">{tags.map((tag) => <span key={tag}>{tag}</span>)}</span>
        </span>
        <span className="shot-chevron" aria-hidden="true">{expanded ? "−" : "+"}</span>
      </button>
      <div className="shot-body">
        <div className="prompt-grid">
          <div className="prompt-box">
            <div className="prompt-box-head">
              <span>PROMPT</span>
              <button type="button" onClick={copyPrompt} disabled={!analysis.prompt}>复制</button>
            </div>
            <p>{analysis.prompt || "该镜头暂未生成 Prompt"}</p>
          </div>
          <div className="prompt-box negative">
            <div className="prompt-box-head"><span>REMAKE NOTES</span></div>
            <p>{notes}</p>
          </div>
        </div>
        <div className="meta-grid">
          <div className="meta-item"><span>SHOT SIZE</span><strong>{analysis.shot_type || "—"}</strong></div>
          <div className="meta-item"><span>CAMERA</span><strong>{analysis.camera_movement || "—"}</strong></div>
          <div className="meta-item"><span>LIGHTING</span><strong>{analysis.lighting || "—"}</strong></div>
          <div className="meta-item"><span>ORIGIN</span><strong>{ORIGIN_LABELS[shot.origin] || shot.origin || "—"}</strong></div>
        </div>
        <div className="shot-actions">
          <a className="btn btn-ghost" href={`/generate?reference=${encodeURIComponent(project.id)}&mode=full`}>用此镜头生成 ↗</a>
        </div>
        <div className="shot-foot">
          <div className="palette-dots">
            {palette.filter(Boolean).map((color, colorIndex) => <i style={{ background: color }} key={`${color}-${colorIndex}`} />)}
            <span>{analysis.visual_style || "镜头色板"}</span>
          </div>
          <span>{formatClock(shot.start_s)} — {formatClock(shot.end_s)}</span>
        </div>
      </div>
    </article>
  );
}
