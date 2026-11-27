import { useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";

import { createProject, estimateCost, fetchHealth } from "../../api/endpoints";
import type { CostEstimate } from "../../api/types";
import { CostEstimateCard } from "../../components/CostEstimateCard";
import { Icon } from "../../components/Icon";
import { useApiQuery } from "../../hooks/useApiQuery";
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
  const healthQuery = useApiQuery((signal) => fetchHealth(signal), []);
  const maxUploadMb = healthQuery.data?.max_upload_mb ?? 500;
  const maxBytes = maxUploadMb * 1024 * 1024;
  const tooLarge = Boolean(file && file.size > maxBytes);

  const selectFile = (nextFile: File | null | undefined) => {
    if (!nextFile) {
      return;
    }
    const looksLikeVideo = nextFile.type.startsWith("video/") || /\.(mp4|mov|webm|mkv|avi|m4v)$/i.test(nextFile.name);
    if (!looksLikeVideo) {
      showToast("请选择 MP4、MOV、WEBM、MKV、AVI 或 M4V 视频", "error");
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
    if (!file || uploading || tooLarge) {
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
      showToast("分析任务已创建，可离开此页稍后回来查看", "success");
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

  const clearFile = () => {
    setFile(null);
    setEstimate(null);
    setDuration(null);
    if (inputRef.current) {
      inputRef.current.value = "";
    }
  };

  const durationLabel = duration === null ? "读取视频时长…" : duration > 0 ? `约 ${duration.toFixed(1)} 秒` : "时长暂不可用";
  const fileSize = file ? `${(file.size / 1048576).toFixed(1)} MB` : "";

  return (
    <section className="rr-card rr-start-card" id="create" aria-labelledby="start-title">
      <div className="rr-start-head">
        <div>
          <span className="rr-step-badge">STEP 01 · 新建分析</span>
          <h2 id="start-title">从一段视频开始</h2>
          <p>支持 3–30 秒短片，画面越清晰，拆解越准确。</p>
        </div>
        <span className="rr-limit-note">MAX {maxUploadMb} MB</span>
      </div>

      <form className="rr-upload-form" onSubmit={submit}>
        <div
          id="upload-video-input"
          className={`rr-upload-zone${file ? " has-file" : ""}${dragging ? " is-dragging" : ""}${tooLarge ? " is-error" : ""}`}
          tabIndex={0}
          role="button"
          aria-label={file ? `已选择 ${file.name}，点击更换视频` : "选择或拖入视频文件"}
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
            accept="video/mp4,video/quicktime,video/webm,video/x-matroska,video/x-msvideo,video/x-m4v"
            hidden
            onChange={(event) => selectFile(event.target.files?.[0])}
          />
          {file ? (
            <div className="rr-selected-file">
              <span className="rr-file-icon"><Icon name="video" size={24} /></span>
              <div className="rr-file-copy">
                <strong>{file.name}</strong>
                <span><Icon name="check" size={13} /> {fileSize} · {durationLabel}</span>
                <small>{tooLarge ? `文件超过服务端 ${maxUploadMb} MB 限制` : "点击此处可更换视频"}</small>
              </div>
              <button
                className="rr-file-remove"
                type="button"
                aria-label="移除已选择视频"
                onClick={(event) => { event.stopPropagation(); clearFile(); }}
              >
                <Icon name="trash" size={16} />
              </button>
            </div>
          ) : (
            <div className="rr-upload-empty">
              <span className="rr-upload-icon"><Icon name="upload" size={27} /></span>
              <strong>拖入视频，或点击选择</strong>
              <p>MP4 · MOV · WEBM · MKV · AVI · M4V</p>
              <span className="rr-upload-hint">选择视频文件 <Icon name="arrow-right" size={13} /></span>
            </div>
          )}
        </div>

        <div className="rr-start-form">
          <label className="rr-input-shell">
            <Icon name="folder" size={16} />
            <span className="sr-only">项目名称</span>
            <input
              type="text"
              placeholder="项目名称（可选）"
              maxLength={80}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
            />
          </label>
          <button className="rr-btn rr-btn-primary" type="submit" disabled={!file || uploading || tooLarge}>
            <Icon name={uploading ? "refresh" : "sparkles"} size={17} className={uploading ? "is-spinning" : ""} />
            {uploading ? "正在上传…" : "开始分析"}
            {!uploading ? <Icon name="arrow-right" size={16} /> : null}
          </button>
        </div>

        {file ? (
          <details className="rr-upload-estimate" open>
            <summary><span>预计分析成本</span><small>{durationLabel}</small><Icon name="chevron-down" size={15} /></summary>
            <CostEstimateCard estimate={estimate} loading={estimating} />
          </details>
        ) : null}

        <div className="rr-start-foot">
          <span><Icon name="clock" size={14} /> 提交后可离开页面，分析会在后台继续运行</span>
          <span><Icon name="check" size={14} /> 自动切分镜头、分析画面并生成 Prompt</span>
        </div>
      </form>
    </section>
  );
}
