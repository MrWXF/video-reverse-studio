const promptState = { currentId: null, timer: null, allPrompts: [] };

const PROMPT_STATUS_LABELS = {
  queued: "排队中",
  running: "生成中",
  done: "已完成",
  failed: "失败",
};

const PROMPT_STEP_HINTS = {
  queued: "等待生成",
  planning: "正在规划镜头",
  validating: "正在校验时长与提示词",
  done: "完成",
  failed: "生成失败",
};

const p$ = (selector, root = document) => root.querySelector(selector);

function pEsc(value) {
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

function pToast(message) {
  const element = p$("#toast");
  if (!element) return;
  element.textContent = message;
  element.classList.remove("hidden");
  clearTimeout(pToast.timer);
  pToast.timer = setTimeout(() => element.classList.add("hidden"), 3200);
}

async function pApi(url, options) {
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

function pClock(value) {
  const total = Math.max(0, Number(value || 0));
  const minutes = Math.floor(total / 60);
  const seconds = total - minutes * 60;
  return String(minutes).padStart(2, "0") + ":" + seconds.toFixed(1).padStart(4, "0");
}

function switchMode(view, syncHash = true) {
  document.querySelectorAll(".mode-tab").forEach((tab) => {
    const active = tab.dataset.view === view;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll(".view").forEach((section) => {
    section.classList.toggle("hidden", section.id !== view + "-view");
  });
  if (syncHash) {
    const hash = view === "generate" ? "#generate" : "#reverse";
    if (window.location.hash !== hash) {
      window.history.replaceState(null, "", hash);
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
  if (view === "generate") {
    loadPromptProjects().catch((error) => pToast(error.message));
  }
}

function stopPromptPolling() {
  if (promptState.timer) {
    clearInterval(promptState.timer);
    promptState.timer = null;
  }
}

async function submitPrompt(event) {
  event.preventDefault();
  const idea = p$("#prompt-idea").value.trim();
  if (idea.length < 2) {
    pToast("请先填写创意描述");
    p$("#prompt-idea").focus();
    return;
  }

  const brief = {
    title: p$("#prompt-title").value.trim(),
    idea,
    target_model: p$("#prompt-model").value,
    duration_s: Number(p$("#prompt-duration").value || 15),
    aspect_ratio: p$("#prompt-aspect").value,
    shot_count: Number(p$("#prompt-shots").value || 4),
    style: p$("#prompt-style").value.trim(),
    mood: p$("#prompt-mood").value.trim(),
    negative_prompt: p$("#prompt-negative").value.trim(),
  };

  const button = p$("#prompt-generate");
  const buttonLabel = button.querySelector(".button-label");
  button.disabled = true;
  if (buttonLabel) buttonLabel.textContent = "正在生成…";
  try {
    const data = await pApi("/api/prompt-projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(brief),
    });
    pToast("提示词任务已创建");
    promptState.currentId = data.prompt_project_id;
    await loadPromptProjects();
    await openPromptProject(data.prompt_project_id);
  } catch (error) {
    pToast(error.message);
  } finally {
    button.disabled = false;
    if (buttonLabel) buttonLabel.textContent = "生成分镜与提示词";
  }
}

async function loadPromptProjects() {
  const projects = await pApi("/api/prompt-projects");
  const box = p$("#prompt-projects");
  const count = p$("#prompt-projects-count");
  if (count) count.textContent = String(projects.length).padStart(2, "0");
  if (!box) return;
  if (!projects.length) {
    box.innerHTML =
      '<div class="panel-empty"><span aria-hidden="true">✦</span><p>还没有方案</p></div>';
    return;
  }

  box.innerHTML = projects
    .map((project, index) => {
      const active = project.id === promptState.currentId ? " is-selected" : "";
      const running = ["queued", "running"].includes(project.status);
      const progress = Math.round((project.progress || 0) * 100);
      const tone = (index % 4) + 1;
      const meta = [
        PROMPT_STATUS_LABELS[project.status] || project.status,
        project.target_model || "generic",
        project.shot_count ? project.shot_count + " shots" : "",
      ].filter(Boolean).join(" · ");
      return (
        '<button class="project-item' + active + '" type="button" data-prompt-id="' + pEsc(project.id) +
          '" data-status="' + pEsc(project.status) + '" aria-label="打开提示词方案 ' + pEsc(project.title) + '">' +
          '<span class="project-thumb tone-project-' + tone + '" aria-hidden="true"></span>' +
          '<span class="project-copy"><strong>' + pEsc(project.title) + '</strong><small>' + pEsc(meta) + '</small></span>' +
          '<i aria-hidden="true">↗</i>' +
          (running ? '<span class="progress-line"><i style="width:' + progress + '%"></i></span>' : "") +
        '</button>'
      );
    })
    .join("");
}

async function openPromptProject(id) {
  promptState.currentId = id;
  stopPromptPolling();
  await loadPromptProjects().catch(() => {});
  const project = await renderPromptProject(id);
  if (project && ["queued", "running"].includes(project.status)) {
    promptState.timer = setInterval(async () => {
      const fresh = await renderPromptProject(id, true);
      if (!fresh || !["queued", "running"].includes(fresh.status)) {
        stopPromptPolling();
        loadPromptProjects().catch(() => {});
      }
    }, 1600);
  }
}

async function renderPromptProject(id, silent = false) {
  try {
    const project = await pApi("/api/prompt-projects/" + id);
    if (promptState.currentId !== id) return project;
    renderPromptDetail(project);
    return project;
  } catch (error) {
    if (!silent) pToast(error.message);
    return null;
  }
}

function promptShotCard(shot, position) {
  const number = String(shot.index || position + 1).padStart(2, "0");
  const tone = (position % 4) + 1;
  const tags = [shot.shot_type, shot.camera_movement, shot.lighting, shot.transition]
    .filter(Boolean)
    .map((item) => '<span>' + pEsc(item) + '</span>')
    .join("");
  const palette = (shot.color_palette || [])
    .filter(Boolean)
    .map((color) => '<i style="background:' + pEsc(color) + '"></i>')
    .join("");
  const subject = shot.subject || "镜头 " + number;
  const action = shot.action || shot.scene || "等待画面描述";
  const negative = shot.negative_prompt || "无额外负向词";
  const duration = Number(shot.duration || (shot.end_s - shot.start_s) || 0);

  return (
    '<article class="story-card tone-' + tone + '">' +
      '<div class="story-cover">' +
        '<div class="story-cover-top"><span class="story-number">' + pEsc(number) + '</span>' +
          '<span class="story-time">' + pEsc(pClock(shot.start_s)) + ' — ' + pEsc(pClock(shot.end_s)) + '</span></div>' +
        '<div class="story-caption"><span>SHOT ' + pEsc(number) + ' / ' + pEsc(shot.shot_type || "SCENE") + '</span>' +
          '<strong>' + pEsc(subject) + '</strong></div>' +
      '</div>' +
      '<div class="story-body">' +
        '<div class="tag-row">' + tags + '</div>' +
        '<div class="story-prompt">' +
          '<div class="story-prompt-head"><span>PROMPT</span>' +
            '<button type="button" data-copy-text="' + pEsc(shot.prompt || "") + '">复制</button></div>' +
          '<p>' + pEsc(shot.prompt || "该镜头暂未生成 Prompt") + '</p>' +
          '<p class="story-negative"><b>Negative:</b> ' + pEsc(negative) + '</p>' +
        '</div>' +
        '<div class="story-meta">' +
          '<div><span>SHOT</span><strong>' + pEsc(shot.shot_type || "—") + '</strong></div>' +
          '<div><span>CAMERA</span><strong>' + pEsc(shot.camera_movement || "—") + '</strong></div>' +
          '<div><span>LIGHT</span><strong>' + pEsc(shot.lighting || "—") + '</strong></div>' +
          '<div><span>TRANSITION</span><strong>' + pEsc(shot.transition || "—") + '</strong></div>' +
        '</div>' +
        '<div class="story-foot"><div class="palette-row" aria-label="镜头色板">' + palette + '</div>' +
          '<span>' + pEsc(duration.toFixed(1)) + 's · ' + pEsc(action) + '</span></div>' +
      '</div>' +
    '</article>'
  );
}

function renderPromptDetail(project) {
  const plan = project.plan || {};
  const shots = plan.shots || [];
  const running = ["queued", "running"].includes(project.status);
  const hasPlan = project.status === "done" && shots.length > 0;
  const statusLabel = PROMPT_STATUS_LABELS[project.status] || project.status;
  const progress = Math.round((project.progress || 0) * 100);
  promptState.allPrompts = shots.map((shot) => shot.prompt || "");

  const progressCard = running
    ? '<div class="progress-card">' +
        '<div class="progress-head"><span>' + pEsc(PROMPT_STEP_HINTS[project.step] || project.step || "生成中") +
          '</span><span>' + progress + '%</span></div>' +
        '<div class="progress-track"><i style="width:' + progress + '%"></i></div>' +
        '<p class="muted">正在生成镜头规划和提示词，请稍候。</p>' +
      '</div>'
    : "";

  const errorCard = project.status === "failed"
    ? '<div class="error-card">' + pEsc(project.error || "生成失败，请重试") + '</div>'
    : "";

  const warnings = (plan.warnings || []).length
    ? '<div class="prompt-warnings">' + (plan.warnings || []).map((item) => pEsc(item)).join("<br>") + '</div>'
    : "";

  const actions = [];
  if (hasPlan) {
    actions.push('<a class="btn btn-secondary" href="' + pEsc(project.export_url) + '" download>下载 Markdown</a>');
    actions.push('<a class="btn btn-ghost" href="' + pEsc(project.export_url) + '?format=json" download>JSON</a>');
    actions.push('<button class="btn btn-ghost" type="button" data-copy-all>复制全部 Prompt</button>');
  }
  if (!running) {
    actions.push('<button class="btn btn-ghost" type="button" data-prompt-regenerate="' + pEsc(project.id) + '">重新生成</button>');
    actions.push('<button class="btn btn-ghost danger-action" type="button" data-prompt-delete="' + pEsc(project.id) + '">删除方案</button>');
  }

  const overview = hasPlan
    ? '<div class="plan-overview">' +
        '<div class="summary-grid">' +
          '<div class="summary-card"><span>PLAN SUMMARY</span><strong>' + pEsc(plan.title || project.title) + '</strong><p>' + pEsc(plan.summary || "已完成镜头规划与提示词生成。") + '</p></div>' +
          '<div class="summary-card"><span>MODEL / FORMAT</span><strong>' + pEsc(plan.target_model || "generic") + '</strong><p>' + pEsc(Number(plan.duration_s || 0).toFixed(1)) + 's · ' + pEsc(plan.aspect_ratio || "—") + ' · ' + shots.length + ' shots</p></div>' +
          '<div class="summary-card"><span>GLOBAL STYLE</span><strong>' + pEsc(plan.global_style || plan.summary || "统一视觉语言") + '</strong><p>' + pEsc(plan.warnings?.length ? "含 " + plan.warnings.length + " 条生成提醒" : "方案已完成，可直接交付") + '</p></div>' +
        '</div>' +
      '</div>'
    : "";

  const storyboard = hasPlan
    ? '<div class="storyboard-intro"><div><span class="panel-kicker">GENERATED STORYBOARD</span><h3>分镜与提示词</h3></div>' +
        '<p>' + shots.length + ' 个镜头 · ' + pEsc(plan.aspect_ratio || "—") + ' · ' + pEsc(plan.target_model || "generic") + '</p></div>' +
      '<div class="storyboard-grid">' + shots.map((shot, index) => promptShotCard(shot, index)).join("") + '</div>'
    : running
      ? '<div class="empty"><span class="empty-icon" aria-hidden="true">✦</span><h3>正在生成分镜</h3><p>正在规划镜头和提示词，请稍候。</p></div>'
      : '<div class="empty"><span class="empty-icon" aria-hidden="true">✦</span><h3>暂无提示词结果</h3><p>重新生成这个方案，或返回左侧创建一个新的 Brief。</p></div>';

  p$("#prompt-detail").innerHTML =
    '<div class="result-head">' +
      '<div><p class="panel-kicker">PROMPT / STORYBOARD</p><h2>' + pEsc(project.title) + '</h2>' +
        '<p>' + (project.shot_count || shots.length || 0) + ' 个镜头 · ' + pEsc(project.target_model || "generic") + ' · ' + pEsc(project.status) + '</p></div>' +
      '<div class="result-actions"><span class="status-pill" data-status="' + pEsc(project.status) + '">' + pEsc(statusLabel) + '</span>' + actions.join("") + '</div>' +
    '</div>' +
    progressCard + errorCard + warnings + overview + storyboard;
}

async function copyText(text) {
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

async function regeneratePromptProject(id) {
  try {
    await pApi("/api/prompt-projects/" + id + "/regenerate", { method: "POST" });
    pToast("已重新开始生成");
    await openPromptProject(id);
  } catch (error) {
    pToast(error.message);
  }
}

async function deletePromptProject(id) {
  if (!confirm("确定删除这个提示词方案？")) return;
  try {
    await pApi("/api/prompt-projects/" + id, { method: "DELETE" });
    if (promptState.currentId === id) {
      promptState.currentId = null;
      stopPromptPolling();
    }
    await loadPromptProjects();
    p$("#prompt-detail").innerHTML =
      '<div class="empty"><span class="empty-icon" aria-hidden="true">✦</span>' +
      '<h3>从一个创意开始</h3><p>填写左侧 Brief，或选择已有方案查看完整分镜。</p></div>';
    pToast("已删除");
  } catch (error) {
    pToast(error.message);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".mode-tab").forEach((tab) => {
    tab.addEventListener("click", () => switchMode(tab.dataset.view));
  });
  p$("#prompt-form").addEventListener("submit", submitPrompt);
  p$("#prompt-refresh").addEventListener("click", () => {
    loadPromptProjects().catch((error) => pToast(error.message));
  });
  p$("#prompt-projects").addEventListener("click", (event) => {
    const item = event.target.closest("[data-prompt-id]");
    if (item) openPromptProject(item.dataset.promptId);
  });
  p$("#prompt-detail").addEventListener("click", async (event) => {
    const copy = event.target.closest("[data-copy-text]");
    if (copy) {
      try {
        const copied = await copyText(copy.dataset.copyText || "");
        pToast(copied ? "Prompt 已复制" : "该镜头暂无 Prompt");
      } catch (_) {
        pToast("复制失败，请手动选择文本");
      }
      return;
    }
    if (event.target.closest("[data-copy-all]")) {
      try {
        const text = promptState.allPrompts.filter(Boolean).join("\n\n");
        const copied = await copyText(text);
        pToast(copied ? "全部 Prompt 已复制" : "暂无可复制的 Prompt");
      } catch (_) {
        pToast("复制失败，请手动选择文本");
      }
      return;
    }
    const regenerate = event.target.closest("[data-prompt-regenerate]");
    if (regenerate) {
      regeneratePromptProject(regenerate.dataset.promptRegenerate);
      return;
    }
    const remove = event.target.closest("[data-prompt-delete]");
    if (remove) deletePromptProject(remove.dataset.promptDelete);
  });

  const initialHash = window.location.hash;
  if (initialHash === "#generate" || initialHash === "#generate-view") {
    switchMode("generate", false);
  }
  window.addEventListener("hashchange", () => {
    if (window.location.hash === "#generate" || window.location.hash === "#generate-view") {
      switchMode("generate", false);
    } else if (window.location.hash === "#reverse" || window.location.hash === "#reverse-view") {
      switchMode("reverse", false);
    }
  });
});
