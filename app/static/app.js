const state = {
  file: null,
  currentId: null,
  currentProject: null,
  timer: null,
  stream: null,
  sseFailures: 0,
  refreshPending: false,
  estimateSeq: 0,
  qualityLoading: false,
  selectedShotId: null,
  timelineBusy: false,
  timelineDrag: null,
};
let recipeCache = { jobId: null, text: "" };

const STATUS_LABELS = {
  uploaded: "待分析",
  queued: "排队中",
  running: "分析中",
  done: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

const ORIGIN_LABELS = {
  filmed: "实拍",
  ai_generated: "AI 生成",
  code_generated: "代码生成",
  unknown: "未知",
};

const STEP_HINTS = {
  probing: "正在读取视频元数据",
  segmenting: "正在检测镜头切换",
  extracting: "正在抽取关键帧",
  transcribing: "正在转写音频",
  analyzing: "正在逐镜分析画面",
  fusing: "正在汇总分镜与节奏",
  timeline_queued: "时间轴修改已排队",
  timeline_probing: "正在重新读取视频",
  timeline_transcribing: "正在校准镜头转录",
  timeline_extracting: "正在重抽关键帧",
  timeline_analyzing: "正在重新分析画面",
  timeline_fusing: "正在重建创作底稿",
  done: "完成",
  failed: "任务失败",
  cancelled: "已取消",
};

const {
  $,
  esc,
  toast,
  api,
  copyText: copyValue,
  formatNumber,
  formatClock,
  formatCost,
  usageMarkup,
} = window.ReelReverse;

function setFile(file) {
  if (!file) return;
  state.file = file;
  const filename = $("#filename");
  if (filename) {
    filename.textContent = file.name + " · " + (file.size / 1048576).toFixed(1) + " MB";
  }
  $("#upload").disabled = false;
  $("#dropzone").classList.add("has-file");
  loadCostEstimate(file).catch(() => {});
}

function resetFile() {
  state.file = null;
  state.estimateSeq += 1;
  const input = $("#file");
  if (input) input.value = "";
  const filename = $("#filename");
  if (filename) filename.textContent = "尚未选择文件";
  const estimate = $("#cost-estimate");
  if (estimate) estimate.classList.add("hidden");
  const body = $("#cost-estimate-body");
  if (body) body.innerHTML = '<p class="cost-estimate-note">选择视频后显示预估。</p>';
  $("#upload").disabled = true;
  $("#dropzone").classList.remove("has-file");
}

function readVideoDuration(file) {
  return new Promise((resolve) => {
    const video = document.createElement("video");
    const url = URL.createObjectURL(file);
    let settled = false;
    let timer = null;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      if (timer) window.clearTimeout(timer);
      video.removeAttribute("src");
      video.load();
      URL.revokeObjectURL(url);
      resolve(value);
    };
    timer = window.setTimeout(() => finish(0), 6000);
    video.preload = "metadata";
    video.onloadedmetadata = () => {
      const duration = Number(video.duration);
      finish(Number.isFinite(duration) && duration > 0 ? duration : 0);
    };
    video.onerror = () => finish(0);
    video.src = url;
  });
}

function compactNumber(value) {
  const number = Number(value || 0);
  if (number >= 1000000) return (number / 1000000).toFixed(1) + "M";
  if (number >= 1000) return (number / 1000).toFixed(1) + "K";
  return formatNumber(number, 0);
}

function costEstimateMarkup(data) {
  const cost = data.cost || {};
  const suggestions = (data.suggestions || [])
    .slice(0, 5)
    .map((item) => '<li>' + esc(item) + '</li>')
    .join("");
  const source = data.shot_count_source === "manual" ? "手动镜头数" : "按时长估算";
  return (
    '<div class="cost-estimate-metrics">' +
      '<div><span>SHOTS</span><strong>' + esc(formatNumber(data.estimated_shots, 0)) + '</strong><small>' + esc(source) + '</small></div>' +
      '<div><span>TOKENS</span><strong>' + esc(compactNumber((cost.prompt_tokens || 0) + (cost.completion_tokens || 0))) + '</strong><small>input + output</small></div>' +
      '<div class="is-cost"><span>EST. COST</span><strong>' + esc(formatCost(cost)) + '</strong><small>' + esc(cost.priced ? "配置单价估算" : "等待配置单价") + '</small></div>' +
    '</div>' +
    '<p class="cost-estimate-note">' + esc(cost.note || "") + '</p>' +
    (suggestions ? '<ul class="cost-estimate-suggestions">' + suggestions + '</ul>' : "")
  );
}

async function loadCostEstimate(file) {
  const card = $("#cost-estimate");
  const body = $("#cost-estimate-body");
  const durationLabel = $("#cost-estimate-duration");
  if (!card || !body) return;
  const sequence = ++state.estimateSeq;
  card.classList.remove("hidden");
  if (durationLabel) durationLabel.textContent = "读取视频时长…";
  body.innerHTML = '<p class="cost-estimate-note">正在读取视频时长并估算…</p>';
  const duration = await readVideoDuration(file);
  if (sequence !== state.estimateSeq || state.file !== file) return;
  if (!duration) {
    if (durationLabel) durationLabel.textContent = "时长不可用";
    body.innerHTML = '<p class="cost-estimate-note">浏览器无法读取视频时长，跳过上传前预估；分析完成后仍会展示实际成本。</p>';
    return;
  }
  if (durationLabel) durationLabel.textContent = "~" + formatNumber(duration, 1) + "s";
  try {
    const estimate = await api("/api/projects/estimate-cost", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ video_duration: duration }),
    });
    if (sequence !== state.estimateSeq || state.file !== file) return;
    body.innerHTML = costEstimateMarkup(estimate);
  } catch (error) {
    if (sequence !== state.estimateSeq || state.file !== file) return;
    body.innerHTML = '<p class="cost-estimate-note">成本预估暂不可用：' + esc(error.message) + '</p>';
  }
}

function formatPercent(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "—";
  return (Number(value) * 100).toFixed(1) + "%";
}

function formatDurationSeconds(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "—";
  const seconds = Math.max(0, Number(value));
  if (seconds < 60) return formatNumber(seconds, 1) + "s";
  const minutes = Math.floor(seconds / 60);
  return minutes + "m " + formatNumber(seconds - minutes * 60, 0) + "s";
}

function qualityKpiMarkup(label, value, detail, tone = "") {
  return (
    '<article class="quality-kpi ' + tone + '">' +
      '<span>' + esc(label) + '</span>' +
      '<strong>' + esc(value) + '</strong>' +
      '<small>' + esc(detail) + '</small>' +
    '</article>'
  );
}

function renderQualitySummary(data) {
  const summary = data.summary || {};
  const box = $("#quality-kpis");
  const accuracy = summary.origin_accuracy;
  const correctionRate = summary.correction_rate;
  const accuracyTone = accuracy !== null && accuracy !== undefined && accuracy < 0.85 ? "is-warning" : "is-good";
  const correctionTone = correctionRate !== null && correctionRate !== undefined && correctionRate > 0.3 ? "is-warning" : "";
  if (!box) return;
  box.innerHTML =
    qualityKpiMarkup(
      "来源判定准确率",
      formatPercent(accuracy),
      (summary.origin_corrections || 0) + " 镜发生来源修正 · 基于人工编辑",
      accuracyTone,
    ) +
    qualityKpiMarkup(
      "镜头修正率",
      formatPercent(correctionRate),
      (summary.edited_shots || 0) + " / " + (summary.shots || 0) + " 镜被人工修改",
      correctionTone,
    ) +
    qualityKpiMarkup(
      "平均处理时长",
      formatDurationSeconds(summary.average_processing_seconds),
      (summary.analysis_runs || 0) + " 次完成分析",
      "",
    ) +
    qualityKpiMarkup(
      "TOKEN 消耗",
      compactNumber(summary.total_tokens || 0),
      (summary.total_calls || 0) + " 次模型调用 · input + output",
      "",
    );
}

function renderQualityFields(data) {
  const fields = data.fields || [];
  const box = $("#quality-fields-body");
  const total = $("#quality-field-total");
  const totalCount = fields.reduce((sum, item) => sum + Number(item.count || 0), 0);
  if (total) total.textContent = totalCount + " 次";
  if (!box) return;
  if (!fields.length) {
    box.innerHTML = '<p class="quality-empty">还没有字段修正记录。编辑镜头后，这里会显示最容易出错的字段。</p>';
    return;
  }
  const maximum = Math.max(...fields.map((item) => Number(item.count || 0)), 1);
  box.innerHTML = fields.map((item) => {
    const width = Math.max(3, (Number(item.count || 0) / maximum) * 100);
    return (
      '<div class="quality-field-row">' +
        '<div class="quality-field-copy"><strong>' + esc(item.label) + '</strong>' +
          '<span>' + esc(item.count) + ' 次 · ' + esc(item.affected_shots || 0) + ' 镜 · 修正率 ' + esc(formatPercent(item.rate)) + '</span></div>' +
        '<div class="quality-field-bar" aria-hidden="true"><i style="width:' + width.toFixed(1) + '%"></i></div>' +
      '</div>'
    );
  }).join("");
}

function renderQualityTrend(data) {
  const trend = data.trend || [];
  const box = $("#quality-trend-body");
  if (!box) return;
  if (!trend.length) {
    box.innerHTML = '<p class="quality-empty">时间窗口内没有趋势数据。</p>';
    return;
  }
  const maximum = Math.max(...trend.map((item) => Number(item.field_corrections || 0)), 1);
  const labelStep = Math.max(1, Math.ceil(trend.length / 7));
  const columns = trend.map((item, index) => {
    const total = Number(item.field_corrections || 0);
    const origin = Number(item.origin_corrections || 0);
    const height = total ? Math.max(4, (total / maximum) * 100) : 0;
    const originHeight = total ? Math.max(0, (origin / total) * 100) : 0;
    const showLabel = index % labelStep === 0 || index === trend.length - 1;
    const label = showLabel ? item.date.slice(5) : "";
    const title = item.date + " · " + total + " 个字段修正 · " + (item.edit_events || 0) + " 次编辑";
    return (
      '<div class="quality-trend-column" title="' + esc(title) + '">' +
        '<span class="quality-trend-bar" style="height:' + height.toFixed(1) + '%">' +
          '<i style="height:' + originHeight.toFixed(1) + '%"></i></span>' +
        '<b>' + esc(label) + '</b>' +
      '</div>'
    );
  }).join("");
  box.innerHTML =
    '<div class="quality-trend-chart" style="--trend-cols:' + trend.length + '">' + columns + '</div>' +
    '<div class="quality-trend-legend"><span><i class="is-total"></i>字段修正</span><span><i class="is-origin"></i>来源修正</span></div>' +
    '<p class="quality-trend-note">柱高表示当天字段修正总量，深色部分为来源判定修正。</p>';
}

function renderQualityProjects(data) {
  const projects = data.projects || [];
  const box = $("#quality-projects-body");
  if (!box) return;
  if (!projects.length) {
    box.innerHTML = '<p class="quality-empty">窗口内没有可展示的项目。</p>';
    return;
  }
  box.innerHTML = projects.map((project) => {
    return (
      '<div class="quality-project-row">' +
        '<div class="quality-project-copy"><strong>' + esc(project.title) + '</strong>' +
          '<small>' + esc(project.shot_count) + ' 镜 · ' + esc(STATUS_LABELS[project.status] || project.status) + '</small></div>' +
        '<div class="quality-project-stats">' +
          '<span><b>' + esc(project.edit_events) + '</b> 事件</span>' +
          '<span><b>' + esc(project.edited_shots) + '</b> 修正镜</span>' +
          '<span><b>' + esc(project.origin_corrections) + '</b> 来源</span>' +
        '</div>' +
        '<button class="btn btn-ghost" type="button" data-quality-project="' + esc(project.id) + '">查看项目</button>' +
      '</div>'
    );
  }).join("");
}

function renderQualitySuggestions(data) {
  const suggestions = data.suggestions || [];
  const box = $("#quality-suggestions-body");
  if (!box) return;
  box.innerHTML = suggestions.length
    ? '<ul class="quality-suggestion-list">' + suggestions.map((item, index) => '<li><b>' + String(index + 1).padStart(2, "0") + '</b><span>' + esc(item) + '</span></li>').join("") + '</ul>'
    : '<p class="quality-empty">暂无可展示的建议。</p>';
}

async function loadQualityDashboard(force = false) {
  const view = $("#quality-view");
  if (!view || state.qualityLoading) return;
  state.qualityLoading = true;
  view.classList.add("is-loading");
  try {
    const data = await api("/api/insights/quality?days=30");
    renderQualitySummary(data);
    renderQualityFields(data);
    renderQualityTrend(data);
    renderQualityProjects(data);
    renderQualitySuggestions(data);
    const windowLabel = $("#quality-window-label");
    const windowNote = $("#quality-window-note");
    if (windowLabel) windowLabel.textContent = "近 " + data.window.days + " 天";
    if (windowNote) {
      windowNote.textContent =
        data.summary.projects + " 个活跃项目 · " + data.summary.shots + " 个镜头 · " +
        data.summary.edit_events + " 次人工修正";
    }
  } catch (error) {
    const box = $("#quality-kpis");
    if (box) {
      box.innerHTML = '<article class="quality-kpi is-warning"><span>QUALITY DATA</span><strong>读取失败</strong><small>' + esc(error.message) + '</small></article>';
    }
    if (force) toast(error.message);
  } finally {
    state.qualityLoading = false;
    view.classList.remove("is-loading");
  }
}

function bindDropzone() {
  const dropzone = $("#dropzone");
  const input = $("#file");
  if (!dropzone || !input) return;
  dropzone.addEventListener("click", () => input.click());
  dropzone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      input.click();
    }
  });
  input.addEventListener("change", () => setFile(input.files[0]));
  ["dragenter", "dragover"].forEach((name) => {
    dropzone.addEventListener(name, (event) => {
      event.preventDefault();
      dropzone.classList.add("dragging");
    });
  });
  ["dragleave", "drop"].forEach((name) => {
    dropzone.addEventListener(name, (event) => {
      event.preventDefault();
      dropzone.classList.remove("dragging");
    });
  });
  dropzone.addEventListener("drop", (event) => {
    const file = event.dataTransfer.files[0];
    if (file) setFile(file);
  });
}

async function upload() {
  if (!state.file) return;
  const button = $("#upload");
  const buttonLabel = button.querySelector(".button-label");
  button.disabled = true;
  if (buttonLabel) buttonLabel.textContent = "上传中…";
  const form = new FormData();
  form.append("file", state.file);
  form.append("title", $("#title").value.trim());
  try {
    const data = await api("/api/projects", { method: "POST", body: form });
    toast("任务已创建，正在分析镜头");
    resetFile();
    $("#title").value = "";
    state.currentId = data.project_id;
    await loadProjects();
    await openProject(data.project_id);
  } catch (error) {
    toast(error.message);
  } finally {
    button.disabled = !state.file;
    if (buttonLabel) buttonLabel.textContent = "开始逆向分析";
  }
}

async function loadProjects() {
  const projects = await api("/api/projects");
  const box = $("#projects");
  const count = $("#projects-count");
  if (count) count.textContent = String(projects.length).padStart(2, "0");
  if (!box) return;
  if (!projects.length) {
    box.innerHTML =
      '<div class="panel-empty"><span aria-hidden="true">◧</span><p>还没有项目</p></div>';
    return;
  }
  box.innerHTML = projects
    .map((project, index) => {
      const active = project.id === state.currentId ? " is-selected" : "";
      const running = ["queued", "running"].includes(project.status);
      const progress = Math.round((project.job?.progress || 0) * 100);
      const duration = project.duration ? project.duration.toFixed(1) + "s" : "—";
      const tone = (index % 4) + 1;
      return (
        '<button class="project-item' + active + '" type="button" data-id="' + esc(project.id) +
        '" data-status="' + esc(project.status) + '" aria-label="打开项目 ' + esc(project.title) + '">' +
        '<span class="project-thumb tone-project-' + tone + '" aria-hidden="true"></span>' +
        '<span class="project-copy"><strong>' + esc(project.title) + '</strong><small>' + duration + " · " +
        esc(STATUS_LABELS[project.status] || project.status) + '</small></span>' +
        '<i aria-hidden="true">↗</i>' +
        (running ? '<span class="progress-line"><i style="width:' + progress + '%"></i></span>' : "") +
        '</button>'
      );
    })
    .join("");
}

function stopPolling() {
  if (state.timer) {
    clearInterval(state.timer);
    state.timer = null;
  }
  if (state.stream) {
    state.stream.close();
    state.stream = null;
  }
  state.sseFailures = 0;
}

function startPolling(id) {
  if (state.timer) clearInterval(state.timer);
  state.timer = setInterval(async () => {
    if (state.currentId !== id) {
      stopPolling();
      return;
    }
    const fresh = await renderProject(id, true);
    if (!fresh || !["queued", "running"].includes(fresh.status)) {
      stopPolling();
      loadProjects().catch(() => {});
    }
  }, 1600);
}

function startJobStream(project) {
  if (!project || !project.job?.id) {
    startPolling(project?.id);
    return;
  }
  stopPolling();
  if (typeof EventSource === "undefined") {
    startPolling(project.id);
    return;
  }
  const projectId = project.id;
  const stream = new EventSource("/api/jobs/" + encodeURIComponent(project.job.id) + "/events");
  state.stream = stream;
  stream.addEventListener("open", () => {
    state.sseFailures = 0;
  });
  stream.addEventListener("progress", async () => {
    if (state.currentId !== projectId || state.refreshPending) return;
    state.refreshPending = true;
    try {
      const fresh = await renderProject(projectId, true);
      if (!fresh || !["queued", "running"].includes(fresh.status)) {
        stopPolling();
        loadProjects().catch(() => {});
      }
    } finally {
      state.refreshPending = false;
    }
  });
  stream.addEventListener("complete", async () => {
    if (state.stream === stream) stopPolling();
    if (state.currentId === projectId) {
      await renderProject(projectId, true);
      loadProjects().catch(() => {});
    }
  });
  stream.addEventListener("error", () => {
    if (state.stream !== stream) return;
    state.sseFailures += 1;
    if (state.sseFailures >= 2) {
      stopPolling();
      startPolling(projectId);
    }
  });
}

function renderEmpty() {
  const detail = $("#detail");
  if (!detail) return;
  detail.innerHTML =
    '<div class="empty"><span class="empty-icon" aria-hidden="true">◧</span>' +
    '<h3>等待一个视频</h3><p>上传素材，或从左侧选择一个已有项目。</p></div>';
}

async function ensureRecipe(project) {
  const jobId = project.job?.id || "";
  if (project.status !== "done") {
    return recipeCache.jobId === jobId ? recipeCache.text : "";
  }
  if (recipeCache.jobId === jobId) {
    return recipeCache.text;
  }
  const response = await fetch(project.recipe_url + "?t=" + Date.now());
  if (!response.ok) return "";
  const text = await response.text();
  recipeCache = { jobId, text };
  return text;
}

function paletteMarkup(colors, className = "palette-dots") {
  return (colors || [])
    .filter(Boolean)
    .map((color) => '<i style="background:' + esc(color) + '"></i>')
    .join("");
}

function shotEditorMarkup(shot, project) {
  const analysis = shot.analysis || {};
  const palette = (analysis.color_palette || []).join(", ");
  return (
    '<form class="shot-editor hidden" data-shot-editor>' +
      '<div class="editor-head"><div><span>EDIT SHOT</span><strong>修正镜头分析</strong></div>' +
        '<p>保存后会重新生成 Recipe，并同步到后续提示词参考。</p></div>' +
      '<div class="editor-grid">' +
        '<label class="field"><span class="field-label">景别</span><input class="input" name="shot_type" value="' + esc(analysis.shot_type || "") + '" /></label>' +
        '<label class="field"><span class="field-label">运镜</span><input class="input" name="camera_movement" value="' + esc(analysis.camera_movement || "") + '" /></label>' +
        '<label class="field"><span class="field-label">主体</span><input class="input" name="subject" value="' + esc(analysis.subject || "") + '" /></label>' +
        '<label class="field"><span class="field-label">场景</span><input class="input" name="scene" value="' + esc(analysis.scene || "") + '" /></label>' +
        '<label class="field"><span class="field-label">视觉风格</span><input class="input" name="visual_style" value="' + esc(analysis.visual_style || "") + '" /></label>' +
        '<label class="field"><span class="field-label">光线</span><input class="input" name="lighting" value="' + esc(analysis.lighting || "") + '" /></label>' +
        '<label class="field editor-wide"><span class="field-label">色板（逗号分隔）</span><input class="input" name="color_palette" value="' + esc(palette) + '" /></label>' +
        '<label class="field editor-wide"><span class="field-label">复刻提示词</span><textarea class="textarea" name="prompt" rows="4">' + esc(analysis.prompt || "") + '</textarea></label>' +
        '<label class="field editor-wide"><span class="field-label">复刻备注</span><textarea class="textarea" name="remake_notes" rows="2">' + esc(analysis.remake_notes || "") + '</textarea></label>' +
        '<label class="field editor-wide"><span class="field-label">口播 / 转录</span><textarea class="textarea" name="transcript" rows="2">' + esc(shot.transcript || "") + '</textarea></label>' +
      '</div>' +
      '<div class="editor-actions">' +
        '<button class="btn btn-ghost" type="button" data-cancel-shot-edit>取消</button>' +
        '<button class="btn btn-primary" type="submit" data-shot-id="' + esc(shot.id) + '" data-project-id="' + esc(project.id) + '">保存并重建 Recipe</button>' +
      '</div>' +
    '</form>'
  );
}

function shotCard(shot, position, project) {
  const analysis = shot.analysis || {};
  const index = String(shot.index).padStart(2, "0");
  const tone = (position % 4) + 1;
  const palette = paletteMarkup(analysis.color_palette);
  const keyframe = shot.keyframe_url
    ? '<img src="' + esc(shot.keyframe_url) + '" alt="镜头 ' + esc(index) + ' 关键帧" loading="lazy" />'
    : '<span class="no-frame">无关键帧</span>';
  const tags = [
    analysis.shot_type,
    analysis.camera_movement,
    analysis.lighting,
    ORIGIN_LABELS[shot.origin] || shot.origin,
  ].filter(Boolean).map((item) => '<span>' + esc(item) + '</span>').join("");
  const prompt = analysis.prompt || "";
  const notes = analysis.remake_notes || (shot.transcript ? "口播：" + shot.transcript : "暂无补充说明");
  const collapsed = position === 0 ? "" : " is-collapsed";
  const expanded = position === 0 ? "true" : "false";
  return (
    '<article class="result-card tone-' + tone + collapsed + '" data-shot-card data-shot-id="' + esc(shot.id) + '">' +
      '<button class="shot-toggle" type="button" data-collapse aria-expanded="' + expanded + '">' +
        '<span class="shot-index">' + esc(index) + '</span>' +
        '<span class="shot-visual">' + keyframe + '<b>' + esc(formatClock(shot.end_s)) + '</b></span>' +
        '<span class="shot-info">' +
          '<h4>镜头 ' + esc(index) + ' · ' + esc(analysis.subject || analysis.shot_type || "画面分析") + '</h4>' +
          '<p>' + esc(analysis.scene || analysis.visual_style || "镜头语言与视觉信息") + '</p>' +
          '<span class="shot-tags">' + tags + '</span>' +
        '</span>' +
        '<span class="shot-chevron" aria-hidden="true">+</span>' +
      '</button>' +
      '<div class="shot-body">' +
        '<div class="prompt-grid">' +
          '<div class="prompt-box">' +
            '<div class="prompt-box-head"><span>PROMPT</span><button type="button" data-copy-text="' + esc(prompt) + '">复制</button></div>' +
            '<p>' + esc(prompt || "该镜头暂未生成 Prompt") + '</p>' +
          '</div>' +
          '<div class="prompt-box negative">' +
            '<div class="prompt-box-head"><span>REMAKE NOTES</span></div>' +
            '<p>' + esc(notes) + '</p>' +
          '</div>' +
        '</div>' +
        '<div class="meta-grid">' +
          '<div class="meta-item"><span>SHOT SIZE</span><strong>' + esc(analysis.shot_type || "—") + '</strong></div>' +
          '<div class="meta-item"><span>CAMERA</span><strong>' + esc(analysis.camera_movement || "—") + '</strong></div>' +
          '<div class="meta-item"><span>LIGHTING</span><strong>' + esc(analysis.lighting || "—") + '</strong></div>' +
          '<div class="meta-item"><span>ORIGIN</span><strong>' + esc(ORIGIN_LABELS[shot.origin] || shot.origin || "—") + '</strong></div>' +
        '</div>' +
        '<div class="shot-actions">' +
          '<button class="btn btn-ghost" type="button" data-edit-shot>编辑分析</button>' +
          '<button class="btn btn-ghost" type="button" data-save-template data-project-id="' + esc(project.id) +
            '" data-shot-id="' + esc(shot.id) + '">存为模板</button>' +
          '<button class="btn btn-ghost" type="button" data-reference-project="' + esc(project.id) +
            '" data-reference-mode="full" data-reference-shot="' + esc(shot.index) + '">用此镜头生成 ↗</button>' +
        '</div>' +
        '<div class="shot-foot">' +
          '<div class="palette-dots">' + palette + '<span>' + esc(analysis.visual_style || "镜头色板") + '</span></div>' +
          '<span>' + esc(formatClock(shot.start_s)) + ' — ' + esc(formatClock(shot.end_s)) + '</span>' +
        '</div>' +
        shotEditorMarkup(shot, project) +
      '</div>' +
    '</article>'
  );
}

function relatedPromptsMarkup(project) {
  const prompts = project.prompt_projects || [];
  if (!prompts.length) return "";
  return (
    '<div class="related-prompts">' +
      '<div><span class="panel-kicker">DERIVED PROMPTS</span><strong>已关联 ' + prompts.length + ' 个提示词方案</strong></div>' +
      '<div class="related-prompt-list">' +
        prompts.map((item) =>
          '<button class="related-prompt-item" type="button" data-open-prompt="' + esc(item.id) + '">' +
            '<span>' + esc(item.title) + '</span><small>' + esc(item.reference_mode || "style") + ' · ' + esc(STATUS_LABELS[item.status] || item.status) + '</small>' +
          '</button>'
        ).join("") +
      '</div>' +
    '</div>'
  );
}

function summaryMarkup(project, shots) {
  const first = shots[0]?.analysis || {};
  const palette = shots.flatMap((shot) => shot.analysis?.color_palette || []).slice(0, 5);
  const average = shots.length ? formatNumber((project.duration || 0) / shots.length, 1) : "—";
  const visual = first.visual_style || first.shot_type || "等待画面分析";
  const scene = [first.subject, first.scene].filter(Boolean).join(" · ") || "镜头信息将在分析完成后出现";
  return (
    '<div class="summary-grid">' +
      '<div class="summary-card"><span>VISUAL STYLE</span><strong>' + esc(visual) + '</strong><p>' + esc(scene) + '</p></div>' +
      '<div class="summary-card"><span>RHYTHM</span><strong>' + shots.length + ' 个镜头</strong><p>平均每镜 ' + esc(average) + 's · ' + esc(formatNumber(project.fps, 1)) + ' fps</p></div>' +
      '<div class="summary-card"><span>PALETTE</span><strong>' + palette.length + ' 色提取</strong><div class="palette-inline" aria-label="主色板">' + paletteMarkup(palette, "palette-inline") + '</div></div>' +
    '</div>'
  );
}

function timelineMinimum(project) {
  const value = Number(project?.timeline_min_shot_seconds);
  return Number.isFinite(value) && value > 0 ? value : 0.8;
}

function timelineTotal(project, shots) {
  const lastEnd = shots.length ? Number(shots[shots.length - 1].end_s || 0) : 0;
  return Math.max(Number(project.duration || 0), lastEnd, 0.1);
}

function timelineContext() {
  const project = state.currentProject;
  if (!project) return null;
  const shots = project.shots || [];
  if (!shots.length) return null;
  const shot = shots.find((item) => String(item.id) === String(state.selectedShotId)) || shots[0];
  state.selectedShotId = shot.id;
  return {
    project,
    shots,
    shot,
    position: shots.indexOf(shot),
    minimum: timelineMinimum(project),
  };
}

function timelineSplitPoint(shot, minimum) {
  const lower = roundTimelineValue(Number(shot.start_s) + minimum);
  const upper = roundTimelineValue(Number(shot.end_s) - minimum);
  if (lower > upper) return null;
  const midpoint = roundTimelineValue((Number(shot.start_s) + Number(shot.end_s)) / 2);
  return Math.min(upper, Math.max(lower, midpoint));
}

function roundTimelineValue(value) {
  return Math.round(Number(value || 0) * 1000) / 1000;
}

function timelineRange(left, right, minimum) {
  return {
    lower: roundTimelineValue(Number(left.start_s) + minimum),
    upper: roundTimelineValue(Number(right.end_s) - minimum),
  };
}

function timelineMarkup(project, shots, running) {
  if (!shots.length) return "";
  const context = timelineContext();
  if (!context) return "";
  const { shot, position, minimum } = context;
  const total = timelineTotal(project, shots);
  const locked = running || state.timelineBusy;
  const splitPoint = timelineSplitPoint(shot, minimum);
  const canSplit = splitPoint !== null;
  const canMerge = position < shots.length - 1;
  const splitValue = splitPoint === null ? "" : splitPoint.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
  const segments = [];
  const handles = [];

  shots.forEach((item, index) => {
    const start = Math.max(0, Number(item.start_s || 0));
    const end = Math.max(start, Number(item.end_s || start));
    const left = (start / total) * 100;
    const width = Math.max(0.4, ((end - start) / total) * 100);
    const tone = (index % 4) + 1;
    const subject = item.analysis?.subject || item.analysis?.shot_type || "镜头";
    const selected = String(item.id) === String(shot.id);
    const frame = item.keyframe_url
      ? '<img class="timeline-segment-frame" src="' + esc(item.keyframe_url) + '" alt="" loading="lazy" />'
      : "";
    segments.push(
      '<button class="timeline-segment tone-' + tone + (selected ? " is-selected" : "") +
        '" type="button" data-timeline-shot="' + esc(item.id) + '" data-shot-start="' + start +
        '" style="left:' + left.toFixed(4) + '%;width:' + width.toFixed(4) + '%" aria-pressed="' +
        String(selected) + '" title="镜头 ' + esc(String(item.index).padStart(2, "0")) + " · " +
        esc(subject) + '">' +
        frame +
        '<span class="timeline-segment-shade"></span>' +
        '<span class="timeline-segment-no">' + esc(String(item.index).padStart(2, "0")) + '</span>' +
        '<span class="timeline-segment-copy"><strong>' + esc(subject) + '</strong><small>' +
          esc(formatClock(start)) + ' — ' + esc(formatClock(end)) + '</small></span>' +
      '</button>'
    );

    if (index < shots.length - 1) {
      const right = shots[index + 1];
      const range = timelineRange(item, right, minimum);
      handles.push(
        '<button class="timeline-handle" type="button" data-timeline-boundary="' + esc(item.id) +
          '" data-boundary="' + roundTimelineValue(item.end_s) + '" data-lower="' + range.lower +
          '" data-upper="' + range.upper + '" role="slider" aria-label="调整镜头 ' +
          esc(String(item.index).padStart(2, "0")) + ' 与下一镜的边界" aria-orientation="horizontal" aria-valuemin="' +
          range.lower + '" aria-valuemax="' + range.upper + '" aria-valuenow="' +
          roundTimelineValue(item.end_s) + '" style="left:' + ((Number(item.end_s) / total) * 100).toFixed(4) +
          '%"' + (locked ? " disabled" : "") + '>' +
          '<span class="timeline-handle-time">' + esc(formatClock(item.end_s)) + '</span>' +
          '<span class="timeline-handle-dot" aria-hidden="true"></span>' +
        '</button>'
      );
    }
  });

  const ticks = [0, 0.25, 0.5, 0.75, 1]
    .map((ratio) => '<span style="left:' + (ratio * 100) + '%">' + esc(formatClock(total * ratio)) + '</span>')
    .join("");
  const rangeCopy = canSplit
    ? '拆分点 ' + roundTimelineValue(Number(shot.start_s) + minimum).toFixed(1) + 's — ' +
      roundTimelineValue(Number(shot.end_s) - minimum).toFixed(1) + 's'
    : '镜头过短，暂不可拆分';

  return (
    '<section class="shot-timeline' + (locked ? " is-locked" : "") + '" data-timeline aria-label="镜头时间轴编辑">' +
      '<div class="timeline-head">' +
        '<div><span class="panel-kicker">TIMELINE EDITOR</span><h3>时间轴结构编辑</h3></div>' +
        '<div class="timeline-head-meta"><strong>' + shots.length + '</strong><span>镜头 · ' +
          esc(formatClock(total)) + '</span></div>' +
      '</div>' +
      '<div class="timeline-stage">' +
        '<div class="timeline-track" data-timeline-track>' + segments.join("") + handles.join("") + '</div>' +
        '<div class="timeline-scale" aria-hidden="true">' + ticks + '</div>' +
      '</div>' +
      '<div class="timeline-actions" data-timeline-actions data-selected-shot-id="' + esc(shot.id) + '">' +
        '<div class="timeline-selection">' +
          '<span>SELECTED SHOT</span>' +
          '<strong data-timeline-selected-label>镜头 ' + esc(String(shot.index).padStart(2, "0")) +
            ' · ' + esc(formatClock(shot.start_s)) + ' — ' + esc(formatClock(shot.end_s)) + '</strong>' +
          '<small>点击镜头定位画面；拖动边界手柄，或聚焦手柄后按 ← → 微调。</small>' +
        '</div>' +
        '<div class="timeline-controls">' +
          '<label class="timeline-split-field"><span>拆分点</span>' +
            '<span class="timeline-input-wrap"><input class="input" data-timeline-split-at type="number" step="0.1" min="' +
              (canSplit ? roundTimelineValue(Number(shot.start_s) + minimum) : "") + '" max="' +
              (canSplit ? roundTimelineValue(Number(shot.end_s) - minimum) : "") + '" value="' + splitValue +
              '" aria-label="新镜头拆分时间（秒）"' + (locked || !canSplit ? " disabled" : "") + ' /><em>s</em></span>' +
          '</label>' +
          '<button class="btn btn-secondary" type="button" data-timeline-split' +
            (locked || !canSplit ? " disabled" : "") + '>拆分镜头</button>' +
          '<button class="btn btn-ghost" type="button" data-timeline-merge' +
            (locked || !canMerge ? " disabled" : "") + '>与下一镜合并</button>' +
          '<button class="btn btn-ghost" type="button" data-timeline-reanalyze' +
            (locked ? " disabled" : "") + '>重抽帧并重分析</button>' +
        '</div>' +
      '</div>' +
      '<p class="timeline-range-hint" data-timeline-range-hint>' + esc(rangeCopy) + '</p>' +
    '</section>'
  );
}

function seekTimelineShot(start) {
  const video = $("#detail .video-pane video");
  if (!video) return;
  const target = Math.max(0, Number(start || 0));
  const seek = () => {
    try {
      video.currentTime = target;
    } catch (_) {
      /* keep the selected shot usable even if the media cannot seek */
    }
  };
  if (video.readyState >= 1) seek();
  else video.addEventListener("loadedmetadata", seek, { once: true });
}

function updateTimelineSelection() {
  const context = timelineContext();
  if (!context) return;
  const { project, shots, shot, position, minimum } = context;
  const running = ["queued", "running"].includes(project.status);
  const locked = running || state.timelineBusy;
  const timeline = $("#detail .shot-timeline");
  if (!timeline) return;
  const splitPoint = timelineSplitPoint(shot, minimum);
  const canSplit = splitPoint !== null;
  const canMerge = position < shots.length - 1;

  timeline.querySelectorAll("[data-timeline-shot]").forEach((segment) => {
    const selected = String(segment.dataset.timelineShot) === String(shot.id);
    segment.classList.toggle("is-selected", selected);
    segment.setAttribute("aria-pressed", String(selected));
  });
  document.querySelectorAll("#detail [data-shot-card]").forEach((card) => {
    card.classList.toggle("is-timeline-selected", String(card.dataset.shotId) === String(shot.id));
  });
  timeline.querySelectorAll("[data-timeline-boundary]").forEach((handle) => {
    handle.disabled = locked;
  });

  const actions = timeline.querySelector("[data-timeline-actions]");
  if (actions) actions.dataset.selectedShotId = String(shot.id);
  const label = timeline.querySelector("[data-timeline-selected-label]");
  if (label) {
    label.textContent = "镜头 " + String(shot.index).padStart(2, "0") + " · " +
      formatClock(shot.start_s) + " — " + formatClock(shot.end_s);
  }
  const splitInput = timeline.querySelector("[data-timeline-split-at]");
  if (splitInput) {
    splitInput.min = canSplit ? String(roundTimelineValue(Number(shot.start_s) + minimum)) : "";
    splitInput.max = canSplit ? String(roundTimelineValue(Number(shot.end_s) - minimum)) : "";
    splitInput.value = splitPoint === null ? "" : String(splitPoint);
    splitInput.disabled = locked || !canSplit;
  }
  const splitButton = timeline.querySelector("[data-timeline-split]");
  if (splitButton) splitButton.disabled = locked || !canSplit;
  const mergeButton = timeline.querySelector("[data-timeline-merge]");
  if (mergeButton) mergeButton.disabled = locked || !canMerge;
  const reanalyzeButton = timeline.querySelector("[data-timeline-reanalyze]");
  if (reanalyzeButton) reanalyzeButton.disabled = locked;
  const hint = timeline.querySelector("[data-timeline-range-hint]");
  if (hint) {
    hint.textContent = canSplit
      ? "拆分点 " + roundTimelineValue(Number(shot.start_s) + minimum).toFixed(1) + "s — " +
        roundTimelineValue(Number(shot.end_s) - minimum).toFixed(1) + "s"
      : "镜头过短，暂不可拆分";
  }
  timeline.classList.toggle("is-locked", locked);
}

async function runTimelineMutation(projectId, url, options, successMessage, revertOnError = false) {
  if (state.timelineBusy) return null;
  state.timelineBusy = true;
  updateTimelineSelection();
  try {
    const result = await api(url, options);
    state.timelineBusy = false;
    recipeCache = { jobId: null, text: "" };
    toast(successMessage);
    const fresh = await renderProject(projectId, true);
    if (fresh) startJobStream(fresh);
    loadProjects().catch(() => {});
    return result;
  } catch (error) {
    state.timelineBusy = false;
    toast(error.message);
    if (revertOnError) await renderProject(projectId, true);
    else updateTimelineSelection();
    return null;
  }
}

async function renderDetail(project) {
  const job = project.job || {};
  const running = ["queued", "running"].includes(project.status);
  const statusLabel = STATUS_LABELS[project.status] || project.status;
  const shots = project.shots || [];
  const progress = Math.round((job.progress || 0) * 100);
  state.currentProject = project;
  const [recipeText, projectUsage] = await Promise.all([
    ensureRecipe(project),
    loadProjectCost(project.id).catch(() => null),
  ]);
  const selectedShot = shots.find((shot) => String(shot.id) === String(state.selectedShotId)) || shots[0];
  state.selectedShotId = selectedShot ? selectedShot.id : null;
  const cards = shots.map((shot, index) => shotCard(shot, index, project)).join("");
  const timelineBlock = timelineMarkup(project, shots, running);

  const progressCard = running
    ? '<div class="progress-card">' +
        '<div class="progress-head"><span>' + esc(STEP_HINTS[job.step] || "处理中") + '</span><span>' + progress + '%</span></div>' +
        '<div class="progress-track"><i style="width:' + progress + '%"></i></div>' +
        '<p class="muted">' + esc(job.step || "queued") + '</p>' +
      '</div>'
    : "";

  const errorCard = ["failed", "cancelled"].includes(project.status)
    ? '<div class="error-card">' + esc(job.error || (project.status === "cancelled" ? "任务已取消" : "分析失败，请重试")) + '</div>'
    : "";

  const downloadActions = project.status === "done"
    ? '<a class="btn btn-secondary" href="' + esc(project.recipe_url) + '" download>下载 VIDEO.md</a>' +
      '<a class="btn btn-ghost" href="' + esc(project.recipe_url) + '?format=json" download>JSON</a>'
    : "";

  const referenceActions = project.status === "done"
    ? '<button class="btn btn-primary" type="button" data-reference-project="' + esc(project.id) + '" data-reference-mode="style">一键生成复刻方案</button>' +
      '<button class="btn btn-ghost" type="button" data-reference-project="' + esc(project.id) + '" data-reference-mode="structure">参考镜头结构</button>'
    : "";

  const taskActions = running
    ? '<button class="btn btn-ghost danger-action" type="button" data-cancel-project="' + esc(project.id) + '">取消分析</button>'
    : ["failed", "cancelled"].includes(project.status)
      ? '<button class="btn btn-primary" type="button" data-retry-project="' + esc(project.id) + '">重新分析</button>'
      : "";

  const mediaBlock =
    '<div class="analysis-media">' +
      '<div class="media-card">' +
        '<div class="media-card-head"><span>SOURCE VIDEO</span><b>PREVIEW</b></div>' +
        '<div class="video-pane"><video controls preload="metadata" src="' + esc(project.video_url) + '"></video></div>' +
      '</div>' +
      '<div class="media-card">' +
        '<div class="media-card-head"><span>CREATIVE RECIPE</span><b>MARKDOWN</b></div>' +
        '<div class="recipe-pane"><pre id="recipe-text">' + esc(recipeText || (running ? "正在生成创作底稿…" : "暂无创作底稿")) + '</pre></div>' +
      '</div>' +
    '</div>';

  const shotSection = shots.length
    ? '<div class="section-bar">' +
        '<div><span>STORYBOARD / ' + shots.length + ' SCENES</span><h3>镜头拆解</h3></div>' +
        '<button class="btn btn-ghost" type="button" data-expand-all>全部展开</button>' +
      '</div>' +
      '<div class="shot-list">' + cards + '</div>'
    : (running
        ? '<div class="empty"><span class="empty-icon" aria-hidden="true">◧</span><h3>正在分析镜头</h3><p>镜头切分与画面分析完成后会自动显示在这里。</p></div>'
        : '<div class="empty"><span class="empty-icon" aria-hidden="true">◧</span><h3>暂无镜头结果</h3><p>分析尚未产出镜头数据，请查看任务状态或重新上传。</p></div>');

  $("#detail").innerHTML =
    '<div class="result-head">' +
      '<div>' +
        '<p class="panel-kicker">ANALYSIS RESULT</p>' +
        '<h2>' + esc(project.title) + '</h2>' +
        '<p>' + project.width + '×' + project.height + ' · ' + formatNumber(project.duration, 1) + 's · ' + formatNumber(project.fps, 1) + ' fps</p>' +
      '</div>' +
      '<div class="result-actions">' +
        '<span class="status-pill" data-status="' + esc(project.status) + '">' + esc(statusLabel) + '</span>' +
        taskActions +
        referenceActions +
        downloadActions +
        '<button class="btn btn-ghost danger-action" type="button" data-delete="' + esc(project.id) + '">删除项目</button>' +
      '</div>' +
    '</div>' +
    relatedPromptsMarkup(project) +
    (shots.length ? summaryMarkup(project, shots) : "") +
    (projectUsage ? usageMarkup(projectUsage, true) : "") +
    progressCard +
    errorCard +
    mediaBlock +
    timelineBlock +
    shotSection;
}

async function renderProject(id, silent = false) {
  try {
    const project = await api("/api/projects/" + id);
    if (state.currentId !== id) return project;
    await renderDetail(project);
    return project;
  } catch (error) {
    if (!silent) toast(error.message);
    return null;
  }
}

async function openProject(id) {
  if (state.currentId !== id) {
    state.selectedShotId = null;
    state.timelineDrag = null;
    state.timelineBusy = false;
  }
  state.currentId = id;
  stopPolling();
  await loadProjects().catch(() => {});
  const project = await renderProject(id);
  if (project && ["queued", "running"].includes(project.status)) {
    startJobStream(project);
  }
}

async function cancelProject(id) {
  if (!confirm("确定取消当前分析任务？")) return;
  try {
    await api("/api/projects/" + id + "/cancel", { method: "POST" });
    stopPolling();
    await openProject(id);
    toast("分析任务已取消");
  } catch (error) {
    toast(error.message);
  }
}

async function reanalyzeProject(id) {
  try {
    await api("/api/projects/" + id + "/analyze", { method: "POST" });
    toast("已重新开始分析");
    await openProject(id);
  } catch (error) {
    toast(error.message);
  }
}

async function deleteProject(id) {
  if (!confirm("确定删除这个项目及其文件？")) return;
  try {
    await api("/api/projects/" + id, { method: "DELETE" });
    if (state.currentId === id) {
      state.currentId = null;
      stopPolling();
      renderEmpty();
    }
    recipeCache = { jobId: null, text: "" };
    await loadProjects();
    toast("已删除");
  } catch (error) {
    toast(error.message);
  }
}

async function loadProjectCost(projectId) {
  return api("/api/projects/" + encodeURIComponent(projectId) + "/cost");
}

function templatePreviewMarkup(shot) {
  const analysis = shot.analysis || {};
  const tags = [analysis.shot_type, analysis.camera_movement, analysis.lighting]
    .filter(Boolean)
    .map((item) => '<span>' + esc(item) + '</span>')
    .join("");
  return (
    '<div class="template-preview-head"><span>FROM SHOT ' + esc(String(shot.index).padStart(2, "0")) + '</span>' +
      '<strong>' + esc(analysis.subject || "镜头分析") + '</strong></div>' +
    '<p>' + esc(analysis.scene || analysis.visual_style || "保存景别、运镜、光线、色板和 Prompt。") + '</p>' +
    '<div class="tag-row">' + tags + '</div>' +
    '<div class="palette-row">' + paletteMarkup(analysis.color_palette) + '</div>'
  );
}

function openTemplateDialog(projectId, shotId) {
  const project = state.currentProject;
  const shot = (project?.shots || []).find((item) => String(item.id) === String(shotId));
  const dialog = $("#template-dialog");
  const form = $("#template-form");
  if (!project || !shot || !dialog || !form) {
    toast("镜头数据尚未加载");
    return;
  }
  form.dataset.projectId = projectId;
  form.dataset.shotId = shotId;
  $("#template-name").value = project.title + " · 镜头 " + String(shot.index).padStart(2, "0");
  $("#template-description").value = "";
  $("#template-category").value = "自定义";
  $("#template-tags").value = "";
  $("#template-prompt-template").value = String((shot.analysis || {}).prompt || "");
  $("#template-preview").innerHTML = templatePreviewMarkup(shot);
  if (typeof dialog.showModal === "function") {
    dialog.showModal();
  } else {
    dialog.setAttribute("open", "");
  }
  $("#template-name").focus();
  $("#template-name").select();
}

function closeTemplateDialog() {
  const dialog = $("#template-dialog");
  if (!dialog) return;
  if (typeof dialog.close === "function") dialog.close();
  else dialog.removeAttribute("open");
}

function bindTemplateDialog() {
  const dialog = $("#template-dialog");
  const form = $("#template-form");
  if (!dialog || !form) return;
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) closeTemplateDialog();
    const placeholder = event.target.closest("[data-insert-template-placeholder]");
    if (!placeholder) return;
    const input = $("#template-prompt-template");
    if (!input) return;
    const token = placeholder.dataset.insertTemplatePlaceholder || "";
    const start = input.selectionStart ?? input.value.length;
    const end = input.selectionEnd ?? start;
    if (typeof input.setRangeText === "function") {
      input.setRangeText(token, start, end, "end");
    } else {
      input.value = input.value.slice(0, start) + token + input.value.slice(end);
    }
    input.focus();
    input.setSelectionRange(start + token.length, start + token.length);
  });
  dialog.querySelectorAll("[data-close-template]").forEach((button) => {
    button.addEventListener("click", closeTemplateDialog);
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = $("#template-name").value.trim();
    if (!name) {
      toast("请填写模板名称");
      $("#template-name").focus();
      return;
    }
    const button = form.querySelector('button[type="submit"]');
    const label = button.textContent;
    button.disabled = true;
    button.textContent = "保存中…";
    try {
      await api(
        "/api/projects/" + encodeURIComponent(form.dataset.projectId) + "/shots/" +
          encodeURIComponent(form.dataset.shotId) + "/save-template",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name,
            description: $("#template-description").value.trim(),
            category: $("#template-category").value.trim() || "自定义",
            tags: $("#template-tags").value.split(/[,，]/).map((item) => item.trim()).filter(Boolean),
            prompt_template: $("#template-prompt-template").value.trim(),
          }),
        }
      );
      closeTemplateDialog();
      toast("镜头模板已保存");
      if (typeof window.refreshShotTemplates === "function") window.refreshShotTemplates();
    } catch (error) {
      toast(error.message);
    } finally {
      button.disabled = false;
      button.textContent = label;
    }
  });
}

function applyStyle(style, persist = true) {
  const next = style === "b" ? "b" : "a";
  document.documentElement.dataset.style = next;
  document.querySelectorAll("[data-style-option]").forEach((button) => {
    const active = button.dataset.styleOption === next;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  const themeMeta = document.querySelector('meta[name="theme-color"]');
  if (themeMeta) themeMeta.setAttribute("content", next === "b" ? "#080b18" : "#f8f5ff");
  if (persist) {
    try {
      localStorage.setItem("reelreverse-style", next);
    } catch (_) {
      /* ignore */
    }
  }
}

function bindStyleSwitch() {
  document.querySelectorAll("[data-style-option]").forEach((button) => {
    button.addEventListener("click", () => applyStyle(button.dataset.styleOption));
  });
  applyStyle(document.documentElement.dataset.style || "a", false);
  window.addEventListener("storage", (event) => {
    if (event.key === "reelreverse-style" && event.newValue) {
      applyStyle(event.newValue, false);
    }
  });
}

function timelineBoundaryContext(leftId) {
  const project = state.currentProject;
  if (!project) return null;
  const shots = project.shots || [];
  const position = shots.findIndex((shot) => String(shot.id) === String(leftId));
  if (position < 0 || position >= shots.length - 1) return null;
  const left = shots[position];
  const right = shots[position + 1];
  return {
    project,
    shots,
    left,
    right,
    position,
    minimum: timelineMinimum(project),
    total: timelineTotal(project, shots),
  };
}

function selectTimelineShot(segment) {
  const context = timelineContext();
  if (!context) return;
  const shot = context.shots.find((item) => String(item.id) === String(segment.dataset.timelineShot));
  if (!shot) return;
  state.selectedShotId = shot.id;
  updateTimelineSelection();
  seekTimelineShot(shot.start_s);
}

function startTimelineBoundaryDrag(event) {
  const handle = event.target.closest("[data-timeline-boundary]");
  if (!handle || handle.disabled || event.button !== 0) return;
  const context = timelineBoundaryContext(handle.dataset.timelineBoundary);
  const track = handle.closest("[data-timeline-track]");
  if (!context || !track) return;
  const leftSegment = track.querySelector('[data-timeline-shot="' + context.left.id + '"]');
  const rightSegment = track.querySelector('[data-timeline-shot="' + context.right.id + '"]');
  if (!leftSegment || !rightSegment) return;

  state.selectedShotId = context.left.id;
  updateTimelineSelection();
  const original = roundTimelineValue(handle.dataset.boundary);
  state.timelineDrag = {
    pointerId: event.pointerId,
    handle,
    track,
    leftSegment,
    rightSegment,
    projectId: context.project.id,
    leftId: context.left.id,
    leftStart: Number(context.left.start_s),
    rightEnd: Number(context.right.end_s),
    total: context.total,
    lower: Number(handle.dataset.lower),
    upper: Number(handle.dataset.upper),
    original,
    boundary: original,
    moved: false,
  };
  handle.classList.add("is-dragging");
  track.classList.add("is-dragging");
  document.body.classList.add("timeline-dragging");
  try {
    handle.setPointerCapture(event.pointerId);
  } catch (_) {
    /* pointer capture is optional */
  }
  event.preventDefault();
}

function updateTimelineBoundaryPreview(clientX) {
  const drag = state.timelineDrag;
  if (!drag) return;
  const rect = drag.track.getBoundingClientRect();
  if (!rect.width) return;
  const raw = ((clientX - rect.left) / rect.width) * drag.total;
  const boundary = roundTimelineValue(Math.min(drag.upper, Math.max(drag.lower, raw)));
  const leftPercent = (drag.leftStart / drag.total) * 100;
  const rightPercent = (drag.rightEnd / drag.total) * 100;
  const boundaryPercent = (boundary / drag.total) * 100;
  drag.leftSegment.style.width = Math.max(0.01, boundaryPercent - leftPercent) + "%";
  drag.rightSegment.style.left = boundaryPercent + "%";
  drag.rightSegment.style.width = Math.max(0.01, rightPercent - boundaryPercent) + "%";
  drag.handle.style.left = boundaryPercent + "%";
  drag.handle.setAttribute("aria-valuenow", String(boundary));
  const label = drag.handle.querySelector(".timeline-handle-time");
  if (label) label.textContent = formatClock(boundary);
  drag.boundary = boundary;
  drag.moved = Math.abs(boundary - drag.original) >= 0.001;
}

async function finishTimelineBoundaryDrag(event, cancelled) {
  const drag = state.timelineDrag;
  if (!drag) return;
  if (event.pointerId !== undefined && event.pointerId !== drag.pointerId) return;
  state.timelineDrag = null;
  drag.handle.classList.remove("is-dragging");
  drag.track.classList.remove("is-dragging");
  document.body.classList.remove("timeline-dragging");
  try {
    if (drag.handle.hasPointerCapture(drag.pointerId)) {
      drag.handle.releasePointerCapture(drag.pointerId);
    }
  } catch (_) {
    /* pointer capture may already be released */
  }

  if (cancelled || !drag.moved) {
    if (cancelled && drag.moved) await renderProject(drag.projectId, true);
    else updateTimelineSelection();
    return;
  }
  await runTimelineMutation(
    drag.projectId,
    "/api/projects/" + encodeURIComponent(drag.projectId) + "/shots/" +
      encodeURIComponent(drag.leftId) + "/boundary",
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ boundary_s: drag.boundary }),
    },
    "边界已调整，正在重新分析相邻镜头",
    true
  );
}

function nudgeTimelineBoundary(handle, delta) {
  if (!handle || handle.disabled || !Number.isFinite(delta) || !delta) return;
  const lower = Number(handle.dataset.lower);
  const upper = Number(handle.dataset.upper);
  const current = Number(handle.dataset.boundary);
  const boundary = roundTimelineValue(Math.min(upper, Math.max(lower, current + delta)));
  if (Math.abs(boundary - current) < 0.001) return;
  const context = timelineBoundaryContext(handle.dataset.timelineBoundary);
  if (!context) return;
  runTimelineMutation(
    context.project.id,
    "/api/projects/" + encodeURIComponent(context.project.id) + "/shots/" +
      encodeURIComponent(context.left.id) + "/boundary",
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ boundary_s: boundary }),
    },
    "边界已微调，正在重新分析相邻镜头",
    true
  );
}

function splitTimelineShot() {
  const context = timelineContext();
  if (!context || state.timelineBusy) return;
  const input = $("#detail [data-timeline-split-at]");
  const splitAt = Number(input?.value);
  const lower = roundTimelineValue(Number(context.shot.start_s) + context.minimum);
  const upper = roundTimelineValue(Number(context.shot.end_s) - context.minimum);
  if (!Number.isFinite(splitAt) || splitAt < lower || splitAt > upper) {
    toast("拆分点必须位于 " + lower.toFixed(1) + "s 到 " + upper.toFixed(1) + "s 之间");
    input?.focus();
    return;
  }
  runTimelineMutation(
    context.project.id,
    "/api/projects/" + encodeURIComponent(context.project.id) + "/shots/" +
      encodeURIComponent(context.shot.id) + "/split",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ split_at: splitAt }),
    },
    "镜头已拆分，正在重新分析"
  );
}

function mergeTimelineShot() {
  const context = timelineContext();
  if (!context || state.timelineBusy) return;
  if (context.position >= context.shots.length - 1) {
    toast("最后一个镜头没有下一镜可合并");
    return;
  }
  const next = context.shots[context.position + 1];
  runTimelineMutation(
    context.project.id,
    "/api/projects/" + encodeURIComponent(context.project.id) + "/shots/merge",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ shot_ids: [context.shot.id, next.id] }),
    },
    "镜头已合并，正在重新分析"
  );
}

function reanalyzeTimelineShot() {
  const context = timelineContext();
  if (!context || state.timelineBusy) return;
  runTimelineMutation(
    context.project.id,
    "/api/projects/" + encodeURIComponent(context.project.id) + "/shots/" +
      encodeURIComponent(context.shot.id) + "/reanalyze",
    { method: "POST" },
    "已开始重抽关键帧并重新分析"
  );
}

function bindDetail() {
  const detail = $("#detail");
  if (!detail) return;
  detail.addEventListener("click", async (event) => {
    const timelineShot = event.target.closest("[data-timeline-shot]");
    if (timelineShot) {
      selectTimelineShot(timelineShot);
      return;
    }
    if (event.target.closest("[data-timeline-split]")) {
      splitTimelineShot();
      return;
    }
    if (event.target.closest("[data-timeline-merge]")) {
      mergeTimelineShot();
      return;
    }
    if (event.target.closest("[data-timeline-reanalyze]")) {
      reanalyzeTimelineShot();
      return;
    }
    const editShot = event.target.closest("[data-edit-shot]");
    if (editShot) {
      const card = editShot.closest("[data-shot-card]");
      const editor = card?.querySelector("[data-shot-editor]");
      if (editor) {
        editor.classList.toggle("hidden");
        if (!editor.classList.contains("hidden")) {
          editor.querySelector("input, textarea")?.focus();
          editor.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
      }
      return;
    }
    const cancelShotEdit = event.target.closest("[data-cancel-shot-edit]");
    if (cancelShotEdit) {
      cancelShotEdit.closest("[data-shot-editor]")?.classList.add("hidden");
      return;
    }
    const saveTemplate = event.target.closest("[data-save-template]");
    if (saveTemplate) {
      openTemplateDialog(saveTemplate.dataset.projectId, saveTemplate.dataset.shotId);
      return;
    }
    const reference = event.target.closest("[data-reference-project]");
    if (reference) {
      if (typeof window.openPromptFromReference === "function") {
        window.openPromptFromReference(
          reference.dataset.referenceProject,
          reference.dataset.referenceMode || "style",
          reference.dataset.referenceShot || null
        );
      }
      return;
    }
    const openPrompt = event.target.closest("[data-open-prompt]");
    if (openPrompt) {
      if (typeof window.openPromptProjectById === "function") {
        window.openPromptProjectById(openPrompt.dataset.openPrompt);
      }
      return;
    }
    const copy = event.target.closest("[data-copy-text]");
    if (copy) {
      const copied = await copyValue(copy.dataset.copyText || "");
      toast(copied ? "Prompt 已复制到剪贴板" : "没有可复制的 Prompt");
      return;
    }
    const cancel = event.target.closest("[data-cancel-project]");
    if (cancel) {
      cancelProject(cancel.dataset.cancelProject);
      return;
    }
    const retry = event.target.closest("[data-retry-project]");
    if (retry) {
      reanalyzeProject(retry.dataset.retryProject);
      return;
    }
    const remove = event.target.closest("[data-delete]");
    if (remove) {
      deleteProject(remove.dataset.delete);
      return;
    }
    const toggle = event.target.closest("[data-collapse]");
    if (toggle) {
      const card = toggle.closest(".result-card");
      if (!card) return;
      const collapsed = card.classList.toggle("is-collapsed");
      toggle.setAttribute("aria-expanded", String(!collapsed));
      return;
    }
    const expandAll = event.target.closest("[data-expand-all]");
    if (expandAll && detail.contains(expandAll)) {
      const cards = Array.from(detail.querySelectorAll(".shot-list .result-card"));
      const allOpen = cards.every((card) => !card.classList.contains("is-collapsed"));
      cards.forEach((card) => {
        card.classList.toggle("is-collapsed", allOpen);
        const button = card.querySelector("[data-collapse]");
        if (button) button.setAttribute("aria-expanded", String(!allOpen));
      });
      expandAll.textContent = allOpen ? "全部展开" : "全部收起";
    }
  });

  detail.addEventListener("pointerdown", startTimelineBoundaryDrag);
  detail.addEventListener("pointermove", (event) => {
    if (!state.timelineDrag || event.pointerId !== state.timelineDrag.pointerId) return;
    updateTimelineBoundaryPreview(event.clientX);
    event.preventDefault();
  });
  detail.addEventListener("pointerup", (event) => {
    finishTimelineBoundaryDrag(event, false);
  });
  detail.addEventListener("pointercancel", (event) => {
    finishTimelineBoundaryDrag(event, true);
  });
  detail.addEventListener("keydown", (event) => {
    const handle = event.target.closest("[data-timeline-boundary]");
    if (!handle || !["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    const step = event.shiftKey ? 0.5 : 0.1;
    const delta = (event.key === "ArrowRight" ? step : -step);
    nudgeTimelineBoundary(handle, delta);
    event.preventDefault();
  });

  detail.addEventListener("submit", async (event) => {
    const form = event.target.closest("[data-shot-editor]");
    if (!form) return;
    event.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    const shotId = button?.dataset.shotId;
    const projectId = button?.dataset.projectId;
    if (!shotId || !projectId) return;
    const data = new FormData(form);
    const payload = {};
    for (const field of ["shot_type", "camera_movement", "subject", "scene", "visual_style", "lighting", "prompt", "remake_notes", "transcript"]) {
      payload[field] = String(data.get(field) ?? "").trim();
    }
    payload.color_palette = String(data.get("color_palette") || "")
      .split(/[,，]/)
      .map((item) => item.trim())
      .filter(Boolean);
    button.disabled = true;
    const label = button.textContent;
    button.textContent = "保存中…";
    try {
      await api("/api/projects/" + projectId + "/shots/" + shotId, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      recipeCache = { jobId: null, text: "" };
      toast("镜头分析已更新，Recipe 已重建");
      await renderProject(projectId);
    } catch (error) {
      toast(error.message);
    } finally {
      button.disabled = false;
      button.textContent = label;
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  bindStyleSwitch();
  bindDropzone();
  bindDetail();
  bindTemplateDialog();
  window.loadQualityDashboard = loadQualityDashboard;
  window.openReverseProject = openProject;
  $("#upload").addEventListener("click", upload);
  $("#refresh").addEventListener("click", () => {
    loadProjects().catch((error) => toast(error.message));
  });
  $("#projects").addEventListener("click", (event) => {
    const item = event.target.closest("[data-id]");
    if (item) openProject(item.dataset.id);
  });
  document.querySelectorAll("[data-mode-target]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = document.querySelector('.mode-tab[data-view="' + button.dataset.modeTarget + '"]');
      if (target) target.click();
    });
  });
  document.querySelectorAll("[data-quality-refresh]").forEach((button) => {
    button.addEventListener("click", () => loadQualityDashboard(true));
  });
  $("#quality-view")?.addEventListener("click", (event) => {
    const projectButton = event.target.closest("[data-quality-project]");
    if (!projectButton) return;
    const target = document.querySelector('.mode-tab[data-view="reverse"]');
    if (target) target.click();
    window.openReverseProject?.(projectButton.dataset.qualityProject);
  });
  loadProjects().catch((error) => toast(error.message));
});
