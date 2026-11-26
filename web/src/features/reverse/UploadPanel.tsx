import { useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";

import { createProject, estimateCost } from "../../api/endpoints";
import type { CostEstimate } from "../../api/types";
import { CostEstimateCard } from "../../components/CostEstimateCard";
import { useUiStore } from "../../store/uiStore";
import { readVideoDuration } from "../../utils/media";

interface UploadPanelProps {
  onCreated: (projectId: string) => void;
}

export function UploadPanel({ onCreated }: UploadPanelProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [duration, setDuration] = useState<number | null>(null);
  const [estimate, setEstimate] = useState<CostEstimate | null>(null);
  const [estimating, setEstimating] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const showToast = useUiStore((state) => state.showToast);

  const selectFile = (nextFile: File | null | undefined) => {
    if (!nextFile) {
      return;
    }
    setFile(nextFile);
    setEstimate(null);
    setDuration(null);
  };

  useEffect(() => {
    if (!file) {
      return undefined;
    }
    let cancelled = false;
    const controller = new AbortController();
    setEstimating(true);

    readVideoDuration(file)
      .then(async (seconds) => {
        if (cancelled) {
          return;
        }
        setDuration(seconds);
        if (seconds <= 0) {
          setEstimate(null);
          return;
        }
        const data = await estimateCost(seconds, controller.signal);
        if (!cancelled) {
          setEstimate(data);
        }
      })
      .catch((error: unknown) => {
        if (!cancelled && !(error instanceof DOMException && error.name === "AbortError")) {
          showToast(error instanceof Error ? error.message : "成本预估失败", "error");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setEstimating(false);
        }
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [file, showToast]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!file || uploading) {
      return;
    }
    const form = new FormData();
    form.append("file", file);
    form.append("title", title.trim());
    setUploading(true);
    try {
      const data = await createProject(form);
      setFile(null);
      setTitle("");
      setEstimate(null);
      setDuration(null);
      if (inputRef.current) {
        inputRef.current.value = "";
      }
      showToast("任务已创建，正在分析镜头", "success");
      onCreated(data.project_id);
    } catch (error) {
      showToast(error instanceof Error ? error.message : "上传失败", "error");
    } finally {
      setUploading(false);
    }
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    selectFile(event.dataTransfer.files[0]);
  };

  const durationLabel = duration === null ? "读取视频时长…" : duration > 0 ? `~${duration.toFixed(1)}s` : "时长不可用";

  return (
    <section className="panel upload-panel" id="create">
      <div className="panel-head">
        <div>
          <p className="panel-kicker">NEW ANALYSIS</p>
          <h2>上传参考视频</h2>
        </div>
        <span className="step-badge">01</span>
      </div>
      <p className="panel-intro">拖入一段 3–30 秒的高质量参考片，系统会自动识别镜头结构与可复用的视觉语言。</p>

      <form onSubmit={submit}>
        <div
          className={`dropzone${file ? " has-file" : ""}${dragging ? " dragging" : ""}`}
          tabIndex={0}
          role="button"
          aria-label="选择或拖入视频文件"
          onClick={() => inputRef.current?.click()}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              inputRef.current?.click();
            }
          }}
          onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
          onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
          onDragLeave={(event) => { event.preventDefault(); setDragging(false); }}
          onDrop={onDrop}
        >
          <input
            ref={inputRef}
            type="file"
            accept="video/mp4,video/quicktime,video/webm,video/x-matroska"
            hidden
            onChange={(event) => selectFile(event.target.files?.[0])}
          />
          <span className="upload-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 16V4" /><path d="m7 9 5-5 5 5" /><path d="M5 16v3a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-3" />
            </svg>
          </span>
          <strong>拖入视频，或点击选择</strong>
          <span>MP4 / MOV / WEBM · 最大 500 MB</span>
          <p className="filename">{file ? `${file.name} · ${(file.size / 1048576).toFixed(1)} MB` : "尚未选择文件"}</p>
        </div>

        <label className="inline-field">
          <span className="field-label">项目名称</span>
          <input
            type="text"
            placeholder="可选，默认使用文件名"
            maxLength={80}
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
        </label>

        {file ? (
          <div className="cost-estimate" aria-live="polite">
            <div className="cost-estimate-head">
              <span>ESTIMATE BEFORE ANALYSIS</span>
              <strong>预计分析成本</strong>
              <small>{durationLabel}</small>
            </div>
            <CostEstimateCard estimate={estimate} loading={estimating} />
          </div>
        ) : null}

        <button className="btn btn-primary block" type="submit" disabled={!file || uploading}>
          <span className="button-label">{uploading ? "上传中…" : "开始逆向分析"}</span>
          <span className="arrow" aria-hidden="true">↗</span>
        </button>
      </form>

      <ul className="mini-features">
        <li>自动切分镜头并抽取关键帧</li>
        <li>识别景别、运镜、光线与色板</li>
        <li>生成可复用的 Prompt 与 Negative</li>
      </ul>
    </section>
  );
}
