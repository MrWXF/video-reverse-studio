const state = { file: null, currentId: null, timer: null };
let recipeCache = { jobId: null, text: "" };

const STATUS_LABELS = {
  uploaded: "待分析",
  queued: "排队中",
  running: "分析中",
  done: "已完成",
  failed: "失败",
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
};

const $ = (selector, root = document) => root.querySelector(selector);

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => {
    return {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[character];
  });
}

function toast(message) {
  const element = $("#toast");
  if (!element) return;
  element.textContent = message;
  element.classList.remove("hidden");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => element.classList.add("hidden"), 3200);
}

async function api(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const data = await response.json();
      detail = data.detail || detail;
    } catch (_) {
      /* ignore */
    }
    throw new Error(detail);
  }
  return response.json();
}

async function copyValue(text) {
  if (!text) return false;
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (_) {
      /* fall through */
    }
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  const copied = document.execCommand("copy");
  area.remove();
  return copied;
}

function formatNumber(value, digits = 1) {
  const number = Number(value || 0);
  return Number.isFinite(number) ? number.toFixed(digits) : "0.0";
}

function formatClock(value) {
  const total = Math.max(0, Number(value || 0));
  const minutes = Math.floor(total / 60);
  const seconds = total - minutes * 60;
  return String(minutes).padStart(2, "0") + ":" + seconds.toFixed(1).padStart(4, "0");
}

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

function shotCard(shot, position) {
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
    '<article class="result-card tone-' + tone + collapsed + '">' +
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
        '<div class="shot-foot">' +
          '<div class="palette-dots">' + palette + '<span>' + esc(analysis.visual_style || "镜头色板") + '</span></div>' +
          '<span>' + esc(formatClock(shot.start_s)) + ' — ' + esc(formatClock(shot.end_s)) + '</span>' +
        '</div>' +
      '</div>' +
    '</article>'
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
  const recipeText = await ensureRecipe(project);
  const cards = shots.map((shot, index) => shotCard(shot, index)).join("");

  const progressCard = running
    ? '<div class="progress-card">' +
        '<div class="progress-head"><span>' + esc(STEP_HINTS[job.step] || "处理中") + '</span><span>' + progress + '%</span></div>' +
        '<div class="progress-track"><i style="width:' + progress + '%"></i></div>' +
        '<p class="muted">' + esc(job.step || "queued") + '</p>' +
      '</div>'
    : "";

  const errorCard = project.status === "failed"
    ? '<div class="error-card">' + esc(job.error || "分析失败，请重试") + '</div>'
    : "";

  const downloadActions = project.status === "done"
    ? '<a class="btn btn-secondary" href="' + esc(project.recipe_url) + '" download>下载 VIDEO.md</a>' +
      '<a class="btn btn-ghost" href="' + esc(project.recipe_url) + '?format=json" download>JSON</a>'
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
        downloadActions +
        '<button class="btn btn-ghost danger-action" type="button" data-delete="' + esc(project.id) + '">删除项目</button>' +
      '</div>' +
    '</div>' +
    (shots.length ? summaryMarkup(project, shots) : "") +
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
    state.timer = setInterval(async () => {
      const fresh = await renderProject(id, true);
      if (!fresh || !["queued", "running"].includes(fresh.status)) {
        stopPolling();
        loadProjects().catch(() => {});
      }
    }, 1600);
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
    const copy = event.target.closest("[data-copy-text]");
    if (copy) {
      const copied = await copyValue(copy.dataset.copyText || "");
      toast(copied ? "Prompt 已复制到剪贴板" : "没有可复制的 Prompt");
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
}

document.addEventListener("DOMContentLoaded", () => {
  bindStyleSwitch();
  bindDropzone();
  bindDetail();
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
