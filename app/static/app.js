const state = {
  file: null,
  currentId: null,
  currentProject: null,
  timer: null,
  stream: null,
  sseFailures: 0,
  refreshPending: false,
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
}

function resetFile() {
  state.file = null;
  const input = $("#file");
  if (input) input.value = "";
  const filename = $("#filename");
  if (filename) filename.textContent = "尚未选择文件";
  $("#upload").disabled = true;
  $("#dropzone").classList.remove("has-file");
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
  const cards = shots.map((shot, index) => shotCard(shot, index, project)).join("");

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

function bindDetail() {
  const detail = $("#detail");
  if (!detail) return;
  detail.addEventListener("click", async (event) => {
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
  loadProjects().catch((error) => toast(error.message));
});
