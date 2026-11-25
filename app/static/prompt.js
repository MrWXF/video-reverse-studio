const promptState = {
  currentId: null,
  timer: null,
  allPrompts: [],
  referenceContext: null,
  currentProject: null,
  stream: null,
  reviewTimer: null,
  templateTimer: null,
  templateLoadSeq: 0,
  selectedTemplateCategory: "",
  selectedTemplateTags: [],
  generationTimer: null,
  sseFailures: 0,
  refreshPending: false,
};

const PROMPT_STATUS_LABELS = {
  queued: "排队中",
  running: "生成中",
  done: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

const PROMPT_STEP_HINTS = {
  queued: "等待生成",
  planning: "正在规划镜头",
  validating: "正在校验时长与提示词",
  done: "完成",
  failed: "生成失败",
  cancelled: "已取消",
};

const GENERATION_STATUS_LABELS = {
  queued: "排队中",
  running: "生成中",
  succeeded: "已完成",
  partial: "部分完成",
  failed: "失败",
  cancelled: "已取消",
};

const {
  $: p$,
  esc: pEsc,
  toast: pToast,
  api: pApi,
  copyText,
  formatClock: pClock,
  usageMarkup: pUsage,
} = window.ReelReverse;

function referencePaletteMarkup(colors) {
  return (colors || [])
    .filter(Boolean)
    .map((color) => '<i style="background:' + pEsc(color) + '"></i>')
    .join("");
}

function promptShotField(shot, field, label, options = {}) {
  const value = shot[field] ?? "";
  if (options.textarea) {
    return (
      '<label class="field' + (options.wide ? " editor-wide" : "") + '"><span class="field-label">' + pEsc(label) + '</span>' +
        '<textarea class="textarea" name="' + field + '" rows="' + (options.rows || 3) + '">' + pEsc(value) + '</textarea></label>'
    );
  }
  return (
    '<label class="field' + (options.wide ? " editor-wide" : "") + '"><span class="field-label">' + pEsc(label) + '</span>' +
      '<input class="input" name="' + field + '" value="' + pEsc(value) + '" /></label>'
  );
}

function promptShotEditorMarkup(shot, project) {
  const locks = new Set(shot.locked_fields || []);
  const lockFields = [
    ["shot_type", "景别"],
    ["camera_movement", "运镜"],
    ["subject", "主体"],
    ["action", "动作"],
    ["scene", "场景"],
    ["lighting", "光线"],
    ["color_palette", "色板"],
    ["prompt", "Prompt"],
    ["negative_prompt", "负向词"],
    ["transition", "转场"],
    ["remake_notes", "备注"],
  ];
  const lockMarkup = lockFields
    .map(
      ([field, label]) =>
        '<label><input type="checkbox" name="locked_fields" value="' + field + '"' +
        (locks.has(field) ? " checked" : "") + ' /> ' + pEsc(label) + '</label>'
    )
    .join("");
  return (
    '<form class="prompt-shot-editor hidden" data-prompt-shot-editor data-shot-index="' + shot.index + '" data-project-id="' + pEsc(project.id) + '">' +
      '<div class="editor-head"><div><span>SHOT CONTROL</span><strong>编辑镜头 ' + String(shot.index).padStart(2, "0") + '</strong></div>' +
        '<p>锁定字段在单镜重生成时保持不变。</p></div>' +
      '<div class="editor-grid">' +
        promptShotField(shot, "shot_type", "景别") +
        promptShotField(shot, "camera_movement", "运镜") +
        promptShotField(shot, "subject", "主体") +
        promptShotField(shot, "action", "动作") +
        promptShotField(shot, "scene", "场景") +
        promptShotField(shot, "lighting", "光线") +
        promptShotField(shot, "transition", "转场") +
        promptShotField(shot, "color_palette", "色板（逗号分隔）", { wide: true }) +
        promptShotField(shot, "prompt", "Prompt", { textarea: true, wide: true, rows: 4 }) +
        promptShotField(shot, "negative_prompt", "Negative Prompt", { textarea: true, wide: true, rows: 2 }) +
        promptShotField(shot, "remake_notes", "制作备注", { textarea: true, wide: true, rows: 2 }) +
      '</div>' +
      '<div class="field-locks"><span>LOCK FIELDS</span><div>' + lockMarkup + '</div></div>' +
      '<div class="editor-actions"><button class="btn btn-ghost" type="button" data-cancel-prompt-edit>取消</button>' +
        '<button class="btn btn-primary" type="submit">保存镜头</button></div>' +
    '</form>'
  );
}

function entityLines(items) {
  return (items || [])
    .map((item) => [item.name || "", item.description || "", item.appearance || "", (item.must_keep || []).join("；")].join(" | "))
    .join("\n");
}

function entityEditorMarkup(project) {
  const bible = project.entity_bible || {};
  const groups = [
    ["characters", "角色", "名称 | 描述 | 外观 | 必须保留项（用；分隔）"],
    ["products", "产品", "名称 | 描述 | 外观 | 必须保留项（用；分隔）"],
    ["wardrobe", "服装", "名称 | 描述 | 外观 | 必须保留项（用；分隔）"],
    ["scenes", "场景", "名称 | 描述 | 外观 | 必须保留项（用；分隔）"],
  ];
  return (
    '<form data-entity-form data-project-id="' + pEsc(project.id) + '" class="entity-editor">' +
      '<div class="editor-grid entity-grid">' +
        groups
          .map(
            ([key, label, placeholder]) =>
              '<label class="field editor-wide"><span class="field-label">' + label + '</span>' +
              '<textarea class="textarea" name="' + key + '" rows="3" placeholder="' + placeholder + '">' +
              pEsc(entityLines(bible[key])) + '</textarea></label>'
          )
          .join("") +
        '<label class="field editor-wide"><span class="field-label">连续性规则（每行一条）</span>' +
          '<textarea class="textarea" name="consistency_rules" rows="3" placeholder="主角始终穿红色风衣">' +
          pEsc((bible.consistency_rules || []).join("\n")) + '</textarea></label>' +
      '</div>' +
      '<div class="editor-actions"><span class="muted">用于统一角色、产品、服装和场景描述，并参与下一次生成。</span>' +
        '<button class="btn btn-primary" type="submit">保存 Entity Bible</button></div>' +
    '</form>'
  );
}

function promptToolsMarkup(project) {
  const hasPlan = project.status === "done" && (project.plan || {}).shots?.length;
  if (!hasPlan) return "";
  return (
    '<div class="prompt-studio-tools">' +
      '<details class="studio-tool" open><summary><div><span class="panel-kicker">VERSION HISTORY</span><strong>方案版本</strong></div>' +
        '<span class="tool-count">' + (project.version_count || 0) + ' 个快照</span></summary>' +
        '<div id="prompt-versions" class="tool-body"><p class="muted">正在读取版本…</p></div></details>' +
      '<details class="studio-tool" open><summary><div><span class="panel-kicker">VERSION DIFF</span><strong>版本 A/B 对比</strong></div>' +
        '<span id="version-compare-status" class="tool-count">选择两个版本</span></summary><div class="tool-body version-compare-tool">' +
        '<form class="version-compare-form" data-version-compare data-project-id="' + pEsc(project.id) + '">' +
          '<label class="field"><span class="field-label">版本 A</span><select class="input" name="left_id" id="version-compare-left"></select></label>' +
          '<span class="version-compare-arrow" aria-hidden="true">→</span>' +
          '<label class="field"><span class="field-label">版本 B</span><select class="input" name="right_id" id="version-compare-right"></select></label>' +
          '<button class="btn btn-primary" type="submit">对比版本</button></form>' +
        '<div id="prompt-version-compare" class="version-compare-result"><p class="muted">加载版本后，选择 A/B 两个快照查看差异。</p></div>' +
        '</div></details>' +
      '<details class="studio-tool" open><summary><div><span class="panel-kicker">SHOT TEMPLATE LIBRARY</span><strong>镜头模板库</strong></div>' +
        '<span id="template-count" class="tool-count">正在读取</span></summary><div class="tool-body template-library">' +
        '<div class="template-filter-deck">' +
          '<label class="field"><span class="field-label">分类</span>' +
            '<select id="template-category-filter" class="input"><option value="">全部分类</option></select></label>' +
          '<label class="field template-search"><span class="field-label">搜索模板</span>' +
            '<input id="template-search" class="input" type="search" placeholder="名称、标签、景别、Prompt…" /></label>' +
          '<button class="btn btn-ghost template-filter-reset" type="button" data-reset-template-filters disabled>清除筛选</button>' +
        '</div>' +
        '<div class="template-tag-filter"><span>标签筛选 · 多选取交集</span>' +
          '<div id="template-tag-filters" class="template-tag-filters"><span class="muted">正在读取标签…</span></div></div>' +
        '<div id="prompt-templates" class="template-list"><p class="muted">正在读取模板…</p></div>' +
        '</div></details>' +
      '<details class="studio-tool"><summary><div><span class="panel-kicker">ENTITY BIBLE</span><strong>角色与资产一致性</strong></div>' +
        '<span class="tool-count">' + ((project.entity_bible || {}).consistency_rules || []).length + ' 条规则</span></summary>' +
        '<div class="tool-body">' + entityEditorMarkup(project) + '</div></details>' +
      (project.reference
        ? '<details class="studio-tool"><summary><div><span class="panel-kicker">INHERITANCE MAP</span><strong>参考 Recipe 对比</strong></div>' +
          '<span class="tool-count">' + pEsc(project.reference.mode || "style") + '</span></summary>' +
          '<div id="prompt-comparison" class="tool-body"><p class="muted">正在计算继承度…</p></div></details>'
        : "") +
      '<details class="studio-tool"><summary><div><span class="panel-kicker">DELIVERY REVIEW</span><strong>成片回测</strong></div>' +
        '<span class="tool-count">镜头 / 风格</span></summary><div class="tool-body">' +
        '<form class="review-upload" data-review-form data-project-id="' + pEsc(project.id) + '">' +
          '<label class="field"><span class="field-label">上传成片进行镜头执行度与风格相似度回测</span>' +
          '<input class="input" type="file" name="file" accept="video/mp4,video/quicktime,video/webm,video/x-matroska" required /></label>' +
          '<button class="btn btn-primary" type="submit">开始回测</button></form>' +
        '<div id="prompt-reviews" class="review-list"><p class="muted">正在读取回测记录…</p></div></div></details>' +
      '<details class="studio-tool"><summary><div><span class="panel-kicker">SHARE ACCESS</span><strong>只读分享与评论</strong></div>' +
        '<span class="tool-count">权限链接</span></summary><div class="tool-body">' +
        '<form class="share-create" data-share-form data-project-id="' + pEsc(project.id) + '">' +
          '<label class="field"><span class="field-label">分享版本</span><select class="input" name="version_id" id="share-version"><option value="">当前版本</option></select></label>' +
          '<label class="field"><span class="field-label">权限</span><select class="input" name="permission"><option value="read">只读</option><option value="comment">可评论</option></select></label>' +
          '<label class="field"><span class="field-label">有效天数</span><input class="input" type="number" name="expires_in_days" min="1" max="365" placeholder="永久" /></label>' +
          '<button class="btn btn-primary" type="submit">创建分享链接</button></form>' +
        '<div id="prompt-shares" class="share-list"><p class="muted">正在读取分享链接…</p></div></div></details>' +
      '<details class="studio-tool"><summary><div><span class="panel-kicker">COST / USAGE</span><strong>本次生成用量</strong></div>' +
        '<span class="tool-count">TOKENS · EST.</span></summary><div class="tool-body"><div id="prompt-cost">' +
        '<p class="muted">正在计算用量…</p></div></div></details>' +
      '<details class="studio-tool generation-tool" open><summary><div><span class="panel-kicker">VIDEO GENERATION</span><strong>从提示词生成视频</strong></div>' +
        '<span id="generation-provider" class="tool-count">读取平台…</span></summary><div class="tool-body generation-body">' +
        '<div id="generation-capability" class="generation-capability"><p class="muted">正在读取生成平台状态…</p></div>' +
        '<div class="generation-actions"><button class="btn btn-primary" type="button" data-start-generation="' + pEsc(project.id) + '">生成全部镜头</button>' +
          '<button class="btn btn-ghost" type="button" data-refresh-generation="' + pEsc(project.id) + '">刷新任务</button></div>' +
        '<div id="prompt-generation-jobs" class="generation-jobs"><p class="muted">正在读取生成任务…</p></div>' +
        '</div></details>' +
    '</div>'
  );
}

async function loadReferenceProjects(selectedId = null) {
  const select = p$("#prompt-reference");
  if (!select) return;
  const previous = selectedId === null ? select.value : selectedId;
  const projects = await pApi("/api/projects");
  const ready = projects.filter((project) => project.status === "done");
  select.innerHTML =
    '<option value="">不使用参考项目</option>' +
    ready
      .map(
        (project) =>
          '<option value="' + pEsc(project.id) + '">' + pEsc(project.title) + " · " +
          (project.shot_count || 0) + " 镜</option>"
      )
      .join("");
  if (select.querySelector('option[value="' + previous + '"]')) {
    select.value = previous;
  }
  const mode = p$("#prompt-reference-mode");
  if (mode) mode.disabled = !select.value;
  if (!select.value) {
    promptState.referenceContext = null;
    renderReferencePreview(null);
  }
}

function renderReferencePreview(context) {
  const box = p$("#reference-preview");
  const mode = p$("#prompt-reference-mode");
  if (!box) return;
  if (!context) {
    box.classList.add("hidden");
    box.innerHTML = "";
    if (mode) mode.disabled = true;
    return;
  }
  const recipe = context.recipe || {};
  const shots = recipe.shots || [];
  const palette = [];
  shots.forEach((shot) => {
    (shot.color_palette || []).forEach((color) => {
      if (color && !palette.includes(color)) palette.push(color);
    });
  });
  box.innerHTML =
    '<div class="reference-preview-head"><div><span>REFERENCE ATTACHED</span><strong>' +
      pEsc(recipe.title || "参考项目") + '</strong></div>' +
      '<button type="button" data-clear-reference>移除</button></div>' +
    '<p>' + pEsc(recipe.summary || "已读取参考项目的镜头配方。") + '</p>' +
    '<div class="reference-preview-meta">' +
      '<span>' + shots.length + ' 个镜头</span>' +
      '<span>' + pEsc(recipe.pacing || "—") + '</span>' +
      '<span>' + pEsc(Number(recipe.duration || 0).toFixed(1)) + 's</span>' +
    '</div>' +
    '<div class="palette-row" aria-label="参考色板">' + referencePaletteMarkup(palette.slice(0, 8)) + '</div>';
  box.classList.remove("hidden");
  if (mode) mode.disabled = false;
}

async function loadReferenceContext() {
  const select = p$("#prompt-reference");
  if (!select?.value) {
    promptState.referenceContext = null;
    renderReferencePreview(null);
    return null;
  }
  const data = await pApi(
    "/api/projects/" + encodeURIComponent(select.value) + "/reference-context"
  );
  promptState.referenceContext = data.reference;
  renderReferencePreview(data.reference);
  return data;
}

function applyReferenceSuggestions(data) {
  const suggested = data?.suggested || {};
  if (suggested.title) p$("#prompt-title").value = suggested.title;
  if (suggested.duration_s) p$("#prompt-duration").value = Math.round(suggested.duration_s);
  if (suggested.aspect_ratio) p$("#prompt-aspect").value = suggested.aspect_ratio;
  if (suggested.shot_count) p$("#prompt-shots").value = suggested.shot_count;
  if (suggested.style) p$("#prompt-style").value = suggested.style;
  if (suggested.mood) p$("#prompt-mood").value = suggested.mood;
}

window.openPromptFromReference = async (projectId, mode = "style", shotIndex = null) => {
  if (!projectId) return;
  switchMode("generate");
  try {
    await loadReferenceProjects(projectId);
    const select = p$("#prompt-reference");
    if (select) select.value = projectId;
    const modeSelect = p$("#prompt-reference-mode");
    if (modeSelect) modeSelect.value = ["style", "structure", "full"].includes(mode) ? mode : "style";
    const data = await loadReferenceContext();
    if (data) {
      applyReferenceSuggestions(data);
      const idea = p$("#prompt-idea");
      if (idea && !idea.value.trim()) {
        const reference = data.reference?.recipe || {};
        if (shotIndex) {
          idea.value = "参考镜头 " + String(shotIndex).padStart(2, "0") + " 的构图、光线和镜头语言，创作一个新的画面。";
        } else {
          const modeLabel = mode === "structure" ? "镜头结构" : mode === "full" ? "逐镜构图与镜头语言" : "视觉风格、光线和节奏";
          const summary = reference.summary ? reference.summary + "；" : "";
          idea.value = "参考《" + (reference.title || "该项目") + "》的" + modeLabel + "，" + summary +
            "创作一支新的短视频，保留镜头节奏、光线和色彩语言，并替换为我的产品与场景。";
        }
      }
      if (idea) idea.focus();
    }
    p$("#brief")?.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    pToast(error.message);
  }
};

window.openPromptProjectById = async (id) => {
  if (!id) return;
  switchMode("generate");
  await openPromptProject(id);
};

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
    const hash = view === "generate" ? "#generate" : view === "quality" ? "#quality" : "#reverse";
    if (window.location.hash !== hash) {
      window.history.replaceState(null, "", hash);
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
  if (view === "generate") {
    loadPromptProjects().catch((error) => pToast(error.message));
    loadReferenceProjects().catch((error) => pToast(error.message));
  } else if (view === "quality") {
    if (typeof window.loadQualityDashboard === "function") {
      window.loadQualityDashboard(true).catch((error) => pToast(error.message));
    }
  } else {
    stopGenerationPolling();
  }
}

function stopGenerationPolling() {
  if (promptState.generationTimer) {
    clearTimeout(promptState.generationTimer);
    promptState.generationTimer = null;
  }
}

function stopPromptPolling() {
  if (promptState.timer) {
    clearInterval(promptState.timer);
    promptState.timer = null;
  }
}

function stopPromptStream() {
  if (promptState.stream) {
    promptState.stream.close();
    promptState.stream = null;
  }
  promptState.sseFailures = 0;
}

function startPromptPolling(id) {
  stopPromptPolling();
  promptState.timer = setInterval(async () => {
    if (promptState.currentId !== id) {
      stopPromptPolling();
      return;
    }
    const fresh = await renderPromptProject(id, true);
    if (!fresh || !["queued", "running"].includes(fresh.status)) {
      stopPromptPolling();
      loadPromptProjects().catch(() => {});
    }
  }, 1600);
}

function startPromptStream(id) {
  stopPromptStream();
  if (typeof EventSource === "undefined") {
    startPromptPolling(id);
    return;
  }
  const stream = new EventSource("/api/prompt-projects/" + encodeURIComponent(id) + "/events");
  promptState.stream = stream;
  stream.addEventListener("open", () => {
    promptState.sseFailures = 0;
  });
  stream.addEventListener("progress", async () => {
    if (promptState.currentId !== id || promptState.refreshPending) return;
    promptState.refreshPending = true;
    try {
      const fresh = await renderPromptProject(id, true);
      if (!fresh || !["queued", "running"].includes(fresh.status)) {
        stopPromptStream();
        loadPromptProjects().catch(() => {});
      }
    } finally {
      promptState.refreshPending = false;
    }
  });
  stream.addEventListener("complete", async () => {
    if (promptState.stream === stream) stopPromptStream();
    if (promptState.currentId === id) {
      await renderPromptProject(id, true);
      loadPromptProjects().catch(() => {});
    }
  });
  stream.addEventListener("error", () => {
    if (promptState.stream !== stream) return;
    promptState.sseFailures += 1;
    if (promptState.sseFailures >= 2) {
      stream.close();
      promptState.stream = null;
      startPromptPolling(id);
    }
  });
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
    reference_project_id: p$("#prompt-reference").value || null,
    reference_mode: p$("#prompt-reference-mode").value || "style",
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
        project.reference ? "↳ " + project.reference.title : "",
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
  stopPromptStream();
  stopGenerationPolling();
  await loadPromptProjects().catch(() => {});
  const project = await renderPromptProject(id);
  if (project && ["queued", "running"].includes(project.status)) {
    startPromptStream(id);
  }
}

async function renderPromptProject(id, silent = false) {
  try {
    const project = await pApi("/api/prompt-projects/" + id);
    if (promptState.currentId !== id) return project;
    renderPromptDetail(project);
    loadPromptAuxiliary(project).catch((error) => pToast(error.message));
    return project;
  } catch (error) {
    if (!silent) pToast(error.message);
    return null;
  }
}

function promptShotCard(shot, position, project) {
  const number = String(shot.index || position + 1).padStart(2, "0");
  const tone = (position % 4) + 1;
  const tags = [shot.shot_type, shot.camera_movement, shot.lighting, shot.transition]
    .filter(Boolean)
    .map((item) => '<span>' + pEsc(item) + '</span>')
    .join("");
  const sourceBadge = shot.source_shot_index
    ? '<span class="shot-source-badge">REF SHOT ' + pEsc(String(shot.source_shot_index).padStart(2, "0")) + '</span>'
    : "";
  const palette = (shot.color_palette || [])
    .filter(Boolean)
    .map((color) => '<i style="background:' + pEsc(color) + '"></i>')
    .join("");
  const subject = shot.subject || "镜头 " + number;
  const action = shot.action || shot.scene || "等待画面描述";
  const negative = shot.negative_prompt || "无额外负向词";
  const duration = Number(shot.duration || (shot.end_s - shot.start_s) || 0);
  const locked = shot.locked_fields || [];
  const lockBadge = locked.length
    ? '<span class="shot-lock-badge">LOCK ' + locked.length + '</span>'
    : "";

  return (
    '<article class="story-card tone-' + tone + '">' +
      '<div class="story-cover">' +
        '<div class="story-cover-top"><span class="story-number">' + pEsc(number) + '</span>' +
          '<span class="story-time">' + pEsc(pClock(shot.start_s)) + ' — ' + pEsc(pClock(shot.end_s)) + '</span></div>' +
        '<div class="story-caption"><span>SHOT ' + pEsc(number) + ' / ' + pEsc(shot.shot_type || "SCENE") + sourceBadge + '</span>' +
          '<strong>' + pEsc(subject) + '</strong></div>' +
      '</div>' +
      '<div class="story-body">' +
        '<div class="tag-row">' + tags + '</div>' +
        '<div class="story-prompt">' +
          '<div class="story-prompt-head"><span>PROMPT ' + lockBadge + '</span>' +
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
        '<div class="prompt-shot-actions">' +
          '<button class="btn btn-ghost" type="button" data-edit-prompt-shot>编辑 / 锁定</button>' +
          '<button class="btn btn-ghost" type="button" data-regenerate-prompt-shot data-shot-index="' + shot.index + '">重生成这镜</button>' +
          '<button class="btn btn-ghost" type="button" data-generate-prompt-shot="' + pEsc(project.id) + '" data-shot-index="' + shot.index + '">生成视频</button>' +
        '</div>' +
        promptShotEditorMarkup(shot, project) +
      '</div>' +
    '</article>'
  );
}

function renderPromptDetail(project) {
  promptState.currentProject = project;
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

  const errorCard = ["failed", "cancelled"].includes(project.status)
    ? '<div class="error-card">' + pEsc(project.error || (project.status === "cancelled" ? "任务已取消" : "生成失败，请重试")) + '</div>'
    : "";

  const warnings = (plan.warnings || []).length
    ? '<div class="prompt-warnings">' + (plan.warnings || []).map((item) => pEsc(item)).join("<br>") + '</div>'
    : "";

  const reference = project.reference;
  const referenceCard = reference
    ? '<div class="reference-source-card">' +
        '<div class="reference-source-copy"><span class="panel-kicker">REFERENCE SOURCE</span>' +
          '<strong>' + pEsc(reference.title || "参考项目") + '</strong>' +
          '<p>' + pEsc(reference.summary || "已基于参考项目生成。") + '</p>' +
          '<div class="reference-preview-meta"><span>' + pEsc(reference.mode || "style") + '</span>' +
            '<span>' + pEsc(reference.shot_count || 0) + ' 镜</span>' +
            '<span>' + pEsc(reference.pacing || "—") + '</span></div></div>' +
        '<div class="reference-source-side"><div class="palette-row">' + referencePaletteMarkup(reference.palette || []) + '</div>' +
          '<button class="btn btn-ghost" type="button" data-open-reference="' + pEsc(reference.project_id) + '">查看参考项目 ↗</button></div>' +
      '</div>'
    : "";

  const actions = [];
  if (hasPlan) {
    actions.push('<a class="btn btn-secondary" href="' + pEsc(project.export_url) + '" download>下载 Markdown</a>');
    actions.push('<a class="btn btn-ghost" href="' + pEsc(project.export_url) + '?format=json" download>JSON</a>');
    actions.push('<a class="btn btn-ghost" href="' + pEsc(project.export_url) + '/zip" download>ZIP 交付包</a>');
    actions.push('<button class="btn btn-ghost" type="button" data-copy-all>复制全部 Prompt</button>');
  }
  if (running) {
    actions.push('<button class="btn btn-ghost danger-action" type="button" data-cancel-prompt="' + pEsc(project.id) + '">取消生成</button>');
  }
  if (!running) {
    actions.push('<button class="btn btn-ghost" type="button" data-prompt-regenerate="' + pEsc(project.id) + '">重新生成</button>');
    actions.push('<button class="btn btn-ghost danger-action" type="button" data-prompt-delete="' + pEsc(project.id) + '">删除方案</button>');
  }

  const overview = hasPlan
    ? '<div class="plan-overview">' +
        '<div class="summary-grid">' +
          '<div class="summary-card"><span>PLAN SUMMARY</span><strong>' + pEsc(plan.title || project.title) + '</strong><p>' + pEsc(plan.summary || "已完成镜头规划与提示词生成。") + '</p></div>' +
          '<div class="summary-card"><span>MODEL / FORMAT</span><strong>' + pEsc((plan.target_profile || {}).label || plan.target_model || "generic") + '</strong><p>' + pEsc(Number(plan.duration_s || 0).toFixed(1)) + 's · ' + pEsc(plan.aspect_ratio || "—") + ' · ' + shots.length + ' shots</p></div>' +
          '<div class="summary-card"><span>GLOBAL STYLE</span><strong>' + pEsc(plan.global_style || plan.summary || "统一视觉语言") + '</strong><p>' + pEsc(plan.warnings?.length ? "含 " + plan.warnings.length + " 条生成提醒" : "方案已完成，可直接交付") + '</p></div>' +
        '</div>' +
      '</div>'
    : "";

  const storyboard = hasPlan
    ? '<div class="storyboard-intro"><div><span class="panel-kicker">GENERATED STORYBOARD</span><h3>分镜与提示词</h3></div>' +
        '<p>' + shots.length + ' 个镜头 · ' + pEsc(plan.aspect_ratio || "—") + ' · ' + pEsc(plan.target_model || "generic") + '</p></div>' +
      '<div class="storyboard-grid">' + shots.map((shot, index) => promptShotCard(shot, index, project)).join("") + '</div>'
    : running
      ? '<div class="empty"><span class="empty-icon" aria-hidden="true">✦</span><h3>正在生成分镜</h3><p>正在规划镜头和提示词，请稍候。</p></div>'
      : '<div class="empty"><span class="empty-icon" aria-hidden="true">✦</span><h3>暂无提示词结果</h3><p>重新生成这个方案，或返回左侧创建一个新的 Brief。</p></div>';

  p$("#prompt-detail").innerHTML =
    '<div class="result-head">' +
      '<div><p class="panel-kicker">PROMPT / STORYBOARD</p><h2>' + pEsc(project.title) + '</h2>' +
        '<p>' + (project.shot_count || shots.length || 0) + ' 个镜头 · ' + pEsc(project.target_model || "generic") + ' · ' + pEsc(statusLabel) + '</p></div>' +
      '<div class="result-actions"><span class="status-pill" data-status="' + pEsc(project.status) + '">' + pEsc(statusLabel) + '</span>' + actions.join("") + '</div>' +
    '</div>' +
    progressCard + errorCard + warnings + referenceCard + overview + promptToolsMarkup(project) + storyboard;
}

const VERSION_SOURCE_LABELS = {
  generate: "初次生成",
  shot_edit: "镜头编辑",
  shot_regenerate: "单镜重生成",
  entity_edit: "Entity Bible",
  restore: "版本恢复",
  template_apply: "套用模板",
};

const VERSION_DIFF_STATUS_LABELS = {
  added: "新增镜头",
  removed: "删除镜头",
  modified: "字段修改",
  unchanged: "无变化",
};

async function loadPromptVersions(projectId) {
  const box = p$("#prompt-versions");
  if (!box) return;
  const versions = await pApi("/api/prompt-projects/" + projectId + "/versions");
  if (!versions.length) {
    box.innerHTML = '<p class="muted">暂时没有版本快照。</p>';
    prepareVersionCompare([]);
    return;
  }
  box.innerHTML =
    '<div class="version-list">' +
    versions
      .map(
        (version) =>
          '<div class="version-item"><span class="version-number">V' + pEsc(String(version.version).padStart(2, "0")) + '</span>' +
          '<div><strong>' + pEsc(VERSION_SOURCE_LABELS[version.source] || version.source) + '</strong>' +
          '<small>' + pEsc(version.title || "未命名方案") + ' · ' + (version.shot_count || 0) + ' 镜 · ' +
          pEsc(version.created_at ? new Date(version.created_at).toLocaleString("zh-CN") : "—") + '</small></div>' +
          '<button class="btn btn-ghost" type="button" data-restore-version="' + pEsc(version.id) + '">恢复</button></div>'
      )
      .join("") +
    '</div>';
  prepareVersionCompare(versions);
}

function versionOptionMarkup(version) {
  return '<option value="' + pEsc(version.id) + '">V' + pEsc(String(version.version).padStart(2, "0")) +
    ' · ' + pEsc(VERSION_SOURCE_LABELS[version.source] || version.source) +
    ' · ' + pEsc(version.title || "未命名方案") + '</option>';
}

function prepareVersionCompare(versions) {
  const left = p$("#version-compare-left");
  const right = p$("#version-compare-right");
  const form = document.querySelector("[data-version-compare]");
  const button = form ? form.querySelector('button[type="submit"]') : null;
  const status = p$("#version-compare-status");
  const box = p$("#prompt-version-compare");
  if (!left || !right) return;

  const previousLeft = left.value;
  const previousRight = right.value;
  const options = versions.map(versionOptionMarkup).join("");
  left.innerHTML = options;
  right.innerHTML = options;
  const available = versions.length >= 2;
  left.disabled = !available;
  right.disabled = !available;
  if (button) button.disabled = !available;

  const fallbackRight = versions[0] ? versions[0].id : "";
  const fallbackLeft = versions[1] ? versions[1].id : fallbackRight;
  left.value = versions.some((item) => item.id === previousLeft) ? previousLeft : fallbackLeft;
  right.value = versions.some((item) => item.id === previousRight) ? previousRight : fallbackRight;
  if (available && left.value === right.value) left.value = fallbackLeft;

  if (status) {
    status.textContent = available ? versions.length + " 个快照可对比" : "至少需要 2 个版本";
  }
  if (!available && box) {
    box.innerHTML = '<p class="muted">先编辑或重生成一次，产生两个版本快照后才能对比。</p>';
  }
}

function versionValueText(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.length ? value.join(" · ") : "空";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function versionVersionLabel(version) {
  return "V" + String((version || {}).version || 0).padStart(2, "0");
}

function versionDiffShotSideMarkup(shot, version, tone) {
  const data = shot || {};
  const exists = Object.keys(data).length > 0;
  return (
    '<article class="version-diff-side ' + tone + (exists ? "" : " is-empty") + '">' +
      '<span>' + pEsc(versionVersionLabel(version)) + '</span>' +
      '<strong>' + pEsc(exists ? (data.subject || data.shot_type || "未命名镜头") : "镜头不存在") + '</strong>' +
      '<p>' + pEsc(exists ? (data.prompt || "未提供 Prompt") : "—") + '</p>' +
      '<small>' + (exists
        ? pEsc(data.shot_type || "—") + ' · ' + pEsc(data.camera_movement || "—") + ' · ' +
          pEsc(Number(data.duration || 0).toFixed(1)) + 's'
        : "—") + '</small>' +
    '</article>'
  );
}

function versionChangeListMarkup(title, changes) {
  if (!changes || !changes.length) return "";
  return (
    '<details class="version-context-changes"><summary><span>' + pEsc(title) + '</span><b>' + changes.length + '</b></summary>' +
      '<div class="version-context-list">' + changes.map((item) =>
        '<div class="version-context-row"><span>' + pEsc(item.label || item.field) + '</span>' +
          '<div><small>' + pEsc(versionValueText(item.left)) + '</small><i>→</i>' +
          '<strong>' + pEsc(versionValueText(item.right)) + '</strong></div></div>'
      ).join("") + '</div></details>'
  );
}

function versionComparisonMarkup(data) {
  const summary = data.summary || {};
  const left = data.left || {};
  const right = data.right || {};
  const fieldTotals = data.field_totals || [];
  const changedShots = (data.shots || []).filter((shot) => shot.status !== "unchanged");
  const durationDelta = Number(summary.duration_delta || 0);
  const durationText = (durationDelta > 0 ? "+" : "") + durationDelta.toFixed(1) + "s";
  const metrics = [
    ["CHANGED SHOTS", (summary.changed_shots || 0) + " / " + Math.max(summary.left_shots || 0, summary.right_shots || 0)],
    ["FIELD CHANGES", summary.field_changes || 0],
    ["ADDED / REMOVED", "+" + (summary.added_shots || 0) + " / −" + (summary.removed_shots || 0)],
    ["DURATION", durationText],
  ];

  return (
    '<div class="version-compare-head">' +
      '<div><span>' + pEsc(versionVersionLabel(left)) + '</span><strong>' + pEsc(VERSION_SOURCE_LABELS[left.source] || left.source || "版本 A") + '</strong>' +
        '<small>' + pEsc(left.title || "未命名方案") + ' · ' + (left.shot_count || 0) + ' 镜</small></div>' +
      '<i aria-hidden="true">→</i>' +
      '<div><span>' + pEsc(versionVersionLabel(right)) + '</span><strong>' + pEsc(VERSION_SOURCE_LABELS[right.source] || right.source || "版本 B") + '</strong>' +
        '<small>' + pEsc(right.title || "未命名方案") + ' · ' + (right.shot_count || 0) + ' 镜</small></div>' +
    '</div>' +
    '<div class="version-compare-kpis">' + metrics.map(([label, value]) =>
      '<div><span>' + label + '</span><strong>' + pEsc(value) + '</strong></div>'
    ).join("") + '</div>' +
    (fieldTotals.length
      ? '<div class="version-field-chips">' + fieldTotals.map((item) =>
          '<span><b>' + pEsc(item.label) + '</b> ×' + pEsc(item.count) + '</span>'
        ).join("") + '</div>'
      : '<p class="version-identical">两个版本的镜头字段一致。</p>') +
    versionChangeListMarkup("方案设置变化", data.plan_changes) +
    versionChangeListMarkup("Brief 变化", data.brief_changes) +
    versionChangeListMarkup("Entity Bible 变化", data.entity_changes) +
    (changedShots.length
      ? '<div class="version-shot-diffs">' + changedShots.map((shot) =>
          '<details class="version-shot-diff is-' + pEsc(shot.status) + '"><summary>' +
            '<span>SHOT ' + pEsc(String(shot.index).padStart(2, "0")) + '</span>' +
            '<div><strong>' + pEsc(VERSION_DIFF_STATUS_LABELS[shot.status] || shot.status) + '</strong>' +
              '<small>' + (shot.status === "modified" ? (shot.changed_fields || []).length + ' 个字段变化' : '版本间镜头增删') + '</small></div>' +
            '<b>' + pEsc(shot.status === "added" ? "+" : shot.status === "removed" ? "−" : "±") + '</b></summary>' +
            '<div class="version-shot-body">' +
              '<div class="version-shot-sides">' +
                versionDiffShotSideMarkup(shot.left, left, "is-left") +
                versionDiffShotSideMarkup(shot.right, right, "is-right") +
              '</div>' +
              ((shot.fields || []).length
                ? '<div class="version-field-diffs">' + shot.fields.map((field) =>
                    '<div class="version-field-diff"><span>' + pEsc(field.label || field.field) + '</span>' +
                      '<div><del>' + pEsc(versionValueText(field.left)) + '</del><ins>' + pEsc(versionValueText(field.right)) + '</ins></div></div>'
                  ).join("") + '</div>'
                : '<p class="version-shot-note">该镜头只存在于一侧版本。</p>') +
            '</div></details>'
        ).join("") + '</div>'
      : '<div class="version-compare-empty">没有镜头级差异，方案级变化如上。</div>') +
    '<p class="version-compare-note">' + pEsc(data.note || "对比不会修改当前方案。") + '</p>'
  );
}

async function comparePromptVersions(projectId, leftId, rightId) {
  const box = p$("#prompt-version-compare");
  const status = p$("#version-compare-status");
  if (!box) return;
  if (!leftId || !rightId) {
    pToast("请选择两个版本");
    return;
  }
  if (leftId === rightId) {
    pToast("请选择两个不同的版本");
    return;
  }
  box.classList.add("is-loading");
  box.innerHTML = '<p class="muted">正在计算版本差异…</p>';
  if (status) status.textContent = "计算中…";
  try {
    const data = await pApi(
      "/api/prompt-projects/" + projectId + "/versions/compare?left_id=" +
      encodeURIComponent(leftId) + "&right_id=" + encodeURIComponent(rightId)
    );
    box.innerHTML = versionComparisonMarkup(data);
    if (status) {
      status.textContent = data.summary.has_changes
        ? (data.summary.changed_shots || 0) + " 镜 / " + (data.summary.field_changes || 0) + " 字段变化"
        : "无差异";
    }
  } catch (error) {
    box.innerHTML = '<p class="error-text">' + pEsc(error.message) + '</p>';
    if (status) status.textContent = "对比失败";
  } finally {
    box.classList.remove("is-loading");
  }
}

function comparisonMarkup(data) {
  const summary = data.summary || {};
  const style = data.style || {};
  const pairs = data.shots || [];
  const score = (value) => Math.round(Number(value || 0) * 100) + "%";
  return (
    '<div class="comparison-summary">' +
      '<div><span>STRUCTURE MATCH</span><strong>' + score(summary.structure_match) + '</strong></div>' +
      '<div><span>PALETTE OVERLAP</span><strong>' + score(summary.palette_overlap) + '</strong></div>' +
      '<div><span>MAPPED SHOTS</span><strong>' + (summary.mapped_shots || 0) + ' / ' + (summary.generated_shots || 0) + '</strong></div>' +
    '</div>' +
    '<div class="comparison-style"><div><span>参考风格</span><strong>' + pEsc(style.reference || "—") + '</strong></div>' +
      '<div><span>生成风格</span><strong>' + pEsc(style.generated || "—") + '</strong></div></div>' +
    '<div class="comparison-list">' +
      pairs
        .map(
          (pair) =>
            '<div class="comparison-row"><div class="comparison-index">REF ' + pEsc(String(pair.source_shot_index).padStart(2, "0")) +
            ' → GEN ' + pEsc(String(pair.generated_shot_index).padStart(2, "0")) + '</div>' +
            '<div><span>' + pEsc(pair.reference.shot_type) + ' · ' + pEsc(pair.reference.camera_movement) + '</span>' +
            '<small>' + pEsc(pair.reference.lighting || "无光线描述") + '</small></div>' +
            '<div><span>' + pEsc(pair.generated.shot_type) + ' · ' + pEsc(pair.generated.camera_movement) + '</span>' +
            '<small>' + pEsc(pair.generated.lighting || "无光线描述") + '</small></div>' +
            '<b>' + score(pair.match_score) + '</b></div>'
        )
        .join("") +
    '</div>'
  );
}

async function loadPromptComparison(projectId) {
  const box = p$("#prompt-comparison");
  if (!box) return;
  const data = await pApi("/api/prompt-projects/" + projectId + "/comparison");
  box.innerHTML = comparisonMarkup(data);
}

function reviewPercent(value) {
  return value === null || value === undefined ? "—" : Math.round(Number(value) * 100) + "%";
}

function reviewMarkup(review) {
  const result = review.result || {};
  const summary = result.summary || {};
  const warnings = result.warnings || [];
  const rows = result.shots || [];
  const progress = Math.round((review.progress || 0) * 100);
  return (
    '<article class="review-item" data-status="' + pEsc(review.status) + '">' +
      '<div class="review-head"><div><strong>' + pEsc(review.filename || "成片回测") + '</strong>' +
        '<small>' + pEsc(PROMPT_STATUS_LABELS[review.status] || review.status) + ' · ' +
        pEsc(review.created_at ? new Date(review.created_at).toLocaleString("zh-CN") : "—") + '</small></div>' +
        '<span class="status-pill" data-status="' + pEsc(review.status) + '">' + pEsc(PROMPT_STATUS_LABELS[review.status] || review.status) + '</span></div>' +
      (["queued", "running"].includes(review.status)
        ? '<div class="progress-track"><i style="width:' + progress + '%"></i></div><p class="muted">正在分析镜头与色彩…</p>'
        : "") +
      (review.status === "failed" ? '<div class="error-card">' + pEsc(review.error || "回测失败") + '</div>' : "") +
      (review.status === "done"
        ? '<div class="review-metrics"><div><span>OVERALL</span><strong>' + reviewPercent(summary.overall_score) + '</strong></div>' +
          '<div><span>EXECUTION</span><strong>' + reviewPercent(summary.execution_score) + '</strong></div>' +
          '<div><span>STYLE</span><strong>' + reviewPercent(summary.style_score) + '</strong></div>' +
          '<div><span>SHOTS</span><strong>' + (summary.actual_shots || 0) + ' / ' + (summary.expected_shots || 0) + '</strong></div></div>' +
          '<div class="review-palettes"><div><span>EXPECTED</span>' + referencePaletteMarkup(result.style?.expected_palette || []) + '</div>' +
            '<div><span>ACTUAL</span>' + referencePaletteMarkup(result.style?.actual_palette || []) + '</div></div>' +
          '<details class="review-shot-details"><summary>查看镜头执行度</summary><div class="review-shot-list">' +
            rows.map((row) => '<div><span>SHOT ' + pEsc(String(row.index).padStart(2, "0")) + '</span>' +
              '<small>' + pEsc(Number(row.actual_duration || 0).toFixed(1)) + 's / ' + pEsc(Number(row.expected_duration || 0).toFixed(1)) + 's</small>' +
              '<b>' + reviewPercent(row.execution_score) + '</b></div>').join("") +
          '</div></details>' +
          (warnings.length ? '<p class="review-note">' + warnings.map((item) => pEsc(item)).join("<br>") + '</p>' : "")
        : "") +
    '</article>'
  );
}

async function loadPromptReviews(projectId) {
  const box = p$("#prompt-reviews");
  if (!box) return;
  const reviews = await pApi("/api/prompt-projects/" + projectId + "/reviews");
  box.innerHTML = reviews.length
    ? reviews.map(reviewMarkup).join("")
    : '<p class="muted">还没有回测记录。上传一版成片即可比较镜头执行度与风格相似度。</p>';
  if (promptState.reviewTimer) {
    clearTimeout(promptState.reviewTimer);
    promptState.reviewTimer = null;
  }
  if (reviews.some((review) => ["queued", "running"].includes(review.status))) {
    promptState.reviewTimer = setTimeout(() => {
      if (promptState.currentId === projectId) {
        loadPromptReviews(projectId).catch((error) => pToast(error.message));
      }
    }, 1600);
  }
}

async function submitReview(form) {
  const projectId = form.dataset.projectId;
  const fileInput = form.querySelector('input[type="file"]');
  if (!fileInput?.files?.length) {
    pToast("请先选择成片文件");
    return;
  }
  const button = form.querySelector('button[type="submit"]');
  if (button) button.disabled = true;
  try {
    const body = new FormData();
    body.append("file", fileInput.files[0]);
    await pApi("/api/prompt-projects/" + projectId + "/reviews", {
      method: "POST",
      body,
    });
    form.reset();
    await loadPromptReviews(projectId);
    pToast("成片已上传，正在回测");
  } catch (error) {
    pToast(error.message);
  } finally {
    if (button) button.disabled = false;
  }
}

function shareAbsoluteUrl(path) {
  return window.location.origin + String(path || "");
}

function shareMarkup(share) {
  const expired = share.revoked_at || (share.expires_at && new Date(share.expires_at) < new Date());
  return (
    '<div class="share-item' + (expired ? " is-revoked" : "") + '"><div class="share-item-copy">' +
      '<strong>' + pEsc(share.permission === "comment" ? "可评论链接" : "只读链接") +
      (share.version_number ? " · V" + pEsc(String(share.version_number).padStart(2, "0")) : " · 当前版本") + '</strong>' +
      '<small>' + (expired ? "已失效" : "有效") + (share.expires_at ? " · 至 " + pEsc(new Date(share.expires_at).toLocaleString("zh-CN")) : " · 长期有效") + '</small></div>' +
      '<div class="share-item-actions"><a class="btn btn-ghost" href="' + pEsc(share.url) + '" target="_blank" rel="noreferrer">打开</a>' +
        '<button class="btn btn-ghost" type="button" data-copy-share="' + pEsc(shareAbsoluteUrl(share.url)) + '">复制链接</button>' +
        (!expired ? '<button class="btn btn-ghost" type="button" data-toggle-share-qr="' + pEsc(share.id) + '" data-share-url="' + pEsc(shareAbsoluteUrl(share.url)) + '" aria-expanded="false">二维码</button>' : "") +
        (!expired ? '<button class="btn btn-ghost danger-action" type="button" data-revoke-share="' + pEsc(share.id) + '">撤销</button>' : "") +
      '</div>' +
      (!expired ? '<div class="share-qr-panel hidden" data-share-qr-panel="' + pEsc(share.id) + '"></div>' : "") +
    '</div>'
  );
}

async function loadPromptShares(projectId) {
  const box = p$("#prompt-shares");
  if (!box) return;
  const [shares, versions] = await Promise.all([
    pApi("/api/prompt-projects/" + projectId + "/shares"),
    pApi("/api/prompt-projects/" + projectId + "/versions"),
  ]);
  const select = p$("#share-version");
  if (select) {
    const previous = select.value;
    select.innerHTML = '<option value="">当前版本</option>' + versions
      .map((version) => '<option value="' + pEsc(version.id) + '">V' + pEsc(String(version.version).padStart(2, "0")) + ' · ' + pEsc(version.title || "未命名方案") + '</option>')
      .join("");
    if (select.querySelector('option[value="' + previous + '"]')) select.value = previous;
  }
  box.innerHTML = shares.length
    ? shares.map(shareMarkup).join("")
    : '<p class="muted">还没有分享链接。选择权限与版本后创建。</p>';
}

async function submitShare(form) {
  const projectId = form.dataset.projectId;
  const data = new FormData(form);
  const expires = Number(data.get("expires_in_days") || 0);
  const button = form.querySelector('button[type="submit"]');
  if (button) button.disabled = true;
  try {
    const share = await pApi("/api/prompt-projects/" + projectId + "/shares", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        permission: data.get("permission") || "read",
        version_id: data.get("version_id") || null,
        expires_in_days: expires || null,
      }),
    });
    await loadPromptShares(projectId);
    const copied = await copyText(shareAbsoluteUrl(share.url));
    pToast(copied ? "分享链接已创建并复制" : "分享链接已创建");
  } catch (error) {
    pToast(error.message);
  } finally {
    if (button) button.disabled = false;
  }
}

async function revokeShare(projectId, shareId) {
  try {
    await pApi("/api/prompt-projects/" + projectId + "/shares/" + shareId, {
      method: "DELETE",
    });
    await loadPromptShares(projectId);
    pToast("分享链接已撤销");
  } catch (error) {
    pToast(error.message);
  }
}

function toggleShareQr(projectId, shareId, button) {
  const panel = Array.from(document.querySelectorAll("[data-share-qr-panel]"))
    .find((item) => item.dataset.shareQrPanel === shareId);
  if (!panel) return;
  const opening = panel.classList.contains("hidden");
  panel.classList.toggle("hidden", !opening);
  button.setAttribute("aria-expanded", String(opening));
  button.textContent = opening ? "收起二维码" : "二维码";
  if (!opening || panel.dataset.loaded === "true") return;

  const qrSrc = "/api/prompt-projects/" + encodeURIComponent(projectId) + "/shares/" +
    encodeURIComponent(shareId) + "/qr.svg";
  panel.innerHTML =
    '<div class="share-qr-card"><div class="share-qr-image"><img src="' + pEsc(qrSrc) + '" alt="分享链接二维码" width="180" height="180" loading="eager" /></div>' +
      '<div class="share-qr-copy"><span>SCAN TO OPEN</span><strong>扫码打开分享页</strong>' +
        '<small>' + pEsc(button.dataset.shareUrl || "") + '</small>' +
        '<button class="btn btn-ghost" type="button" data-copy-share="' + pEsc(button.dataset.shareUrl || "") + '">复制链接</button></div></div>';
  panel.dataset.loaded = "true";
}

function renderTemplateFacets(facets) {
  const categories = Array.isArray(facets?.categories) ? facets.categories : [];
  const categorySelect = p$("#template-category-filter");
  if (categorySelect) {
    const availableCategories = new Set(categories.map((item) => item.value));
    if (
      promptState.selectedTemplateCategory &&
      !availableCategories.has(promptState.selectedTemplateCategory)
    ) {
      promptState.selectedTemplateCategory = "";
    }
    categorySelect.innerHTML =
      '<option value="">全部分类</option>' +
      categories
        .map(
          (item) =>
            '<option value="' + pEsc(item.value) + '">' + pEsc(item.value) +
            ' · ' + Number(item.count || 0) + '</option>'
        )
        .join("");
    categorySelect.value = promptState.selectedTemplateCategory;
  }

  const tagsBox = p$("#template-tag-filters");
  if (!tagsBox) return;
  const tags = Array.isArray(facets?.tags) ? facets.tags : [];
  const availableTags = new Set(tags.map((item) => item.value));
  promptState.selectedTemplateTags = promptState.selectedTemplateTags.filter((tag) =>
    availableTags.has(tag)
  );
  tagsBox.innerHTML = tags.length
    ? tags
        .map((item) => {
          const selected = promptState.selectedTemplateTags.includes(item.value);
          return (
            '<button class="template-tag-chip' + (selected ? " is-selected" : "") +
              '" type="button" data-template-tag-filter="' + pEsc(item.value) +
              '" aria-pressed="' + selected + '"><span>#' + pEsc(item.value) +
              '</span><b>' + Number(item.count || 0) + '</b></button>'
          );
        })
        .join("")
    : '<span class="muted">暂无标签</span>';
}

function templateItemMarkup(template) {
  const tags = (template.tags || [])
    .filter(Boolean)
    .map((tag) => '<span>' + pEsc(tag) + '</span>')
    .join("");
  const meta = [template.shot_type, template.camera_movement, template.lighting]
    .filter(Boolean)
    .map((item) => '<span>' + pEsc(item) + '</span>')
    .join("");
  const placeholders = template.placeholders || [];
  const placeholderBadge = template.has_placeholders
    ? '<span class="template-placeholder-badge" title="' +
      pEsc(placeholders.map((item) => "{{" + item + "}}").join(", ")) + '">' +
      placeholders.length + ' 个占位符</span>'
    : "";
  return (
    '<article class="template-item" data-template-id="' + pEsc(template.id) + '">' +
      '<div class="template-item-head"><div><span>' + pEsc(template.category || "自定义") + '</span>' +
        '<strong>' + pEsc(template.name) + '</strong></div>' +
        '<button class="btn btn-ghost danger-action" type="button" data-delete-template="' + pEsc(template.id) + '">删除</button></div>' +
      (template.description ? '<p>' + pEsc(template.description) + '</p>' : '') +
      (tags ? '<div class="tag-row">' + tags + '</div>' : '') +
      '<div class="template-meta">' + (meta || '<span>通用镜头模板</span>') + placeholderBadge + '</div>' +
      (template.color_palette?.length ? '<div class="palette-row">' + referencePaletteMarkup(template.color_palette) + '</div>' : '') +
      '<div class="template-actions">' +
        '<button class="btn btn-ghost" type="button" data-apply-template="' + pEsc(template.id) + '" data-apply-mode="style">套用风格</button>' +
        '<button class="btn btn-ghost" type="button" data-apply-template="' + pEsc(template.id) + '" data-apply-mode="full">套用 + Prompt</button>' +
      '</div>' +
    '</article>'
  );
}

async function loadPromptTemplates() {
  const box = p$("#prompt-templates");
  if (!box) return;
  const search = (p$("#template-search")?.value || "").trim();
  const count = p$("#template-count");
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  if (promptState.selectedTemplateCategory) {
    params.set("category", promptState.selectedTemplateCategory);
  }
  promptState.selectedTemplateTags.forEach((tag) => params.append("tags", tag));
  const requestSeq = ++promptState.templateLoadSeq;
  if (count) count.textContent = "筛选中…";
  const query = params.toString();
  const [templates, facets] = await Promise.all([
    pApi("/api/shot-templates" + (query ? "?" + query : "")),
    pApi("/api/shot-templates/facets"),
  ]);
  if (requestSeq !== promptState.templateLoadSeq) return;
  renderTemplateFacets(facets);
  const filtering = Boolean(
    search || promptState.selectedTemplateCategory || promptState.selectedTemplateTags.length
  );
  if (count) {
    const total = facets?.total ?? templates.length;
    count.textContent = filtering
      ? templates.length + " / " + total + " 个模板"
      : total + " 个模板";
  }
  const reset = p$("[data-reset-template-filters]");
  if (reset) reset.disabled = !filtering;
  box.innerHTML = templates.length
    ? templates.map(templateItemMarkup).join("")
    : '<p class="muted">还没有匹配的模板。先在逆向镜头里点击“存为模板”。</p>';
}

async function loadPromptCost(projectId) {
  const box = p$("#prompt-cost");
  if (!box) return;
  const usage = await pApi("/api/prompt-projects/" + projectId + "/cost");
  box.innerHTML = pUsage(usage, true);
}

function generationShotMarkup(item) {
  const index = String(item.shot_index || 0).padStart(2, "0");
  const status = GENERATION_STATUS_LABELS[item.status] || item.status || "未知";
  const warnings = (item.warnings || []).filter(Boolean);
  const mediaType = String(item.media_type || "");
  const media = item.status === "succeeded" && item.download_url
    ? mediaType.startsWith("image/")
      ? '<img class="generation-media" src="' + pEsc(item.download_url) + '" alt="镜头 ' + pEsc(index) + ' 生成结果" loading="lazy" />'
      : '<video class="generation-media" src="' + pEsc(item.download_url) + '" controls preload="metadata"></video>'
    : "";
  const size = item.size_bytes ? (Number(item.size_bytes) / 1024).toFixed(0) + " KB" : "";
  return (
    '<div class="generation-shot" data-status="' + pEsc(item.status) + '">' +
      '<div class="generation-shot-head"><div><span>SHOT ' + pEsc(index) + '</span><strong>' + pEsc(status) + '</strong></div>' +
        (item.download_url ? '<a class="btn btn-ghost" href="' + pEsc(item.download_url) + '" download>下载</a>' : '') + '</div>' +
      media +
      '<div class="generation-shot-meta"><span>' + pEsc(Number(item.duration_s || 0).toFixed(1)) + 's</span>' +
        (size ? '<span>' + pEsc(size) + '</span>' : '') + '</div>' +
      (warnings.length ? '<p class="generation-note">' + warnings.map((warning) => pEsc(warning)).join("<br>") + '</p>' : '') +
      (item.error ? '<p class="generation-error">' + pEsc(item.error) + '</p>' : '') +
    '</div>'
  );
}

function generationJobMarkup(job) {
  const active = ["queued", "running"].includes(job.status);
  const status = GENERATION_STATUS_LABELS[job.status] || job.status;
  const shots = (job.result || {}).shots || [];
  const progress = Math.round(Number(job.progress || 0) * 100);
  return (
    '<article class="generation-job" data-status="' + pEsc(job.status) + '">' +
      '<div class="generation-job-head"><div><span class="panel-kicker">' + pEsc(job.provider || "provider") + ' / ' +
        pEsc(job.model || "default") + '</span><strong>' + pEsc(status) + '</strong>' +
        '<small>' + pEsc(job.shot_count || 0) + ' 个镜头 · ' +
          pEsc(job.created_at ? new Date(job.created_at).toLocaleString("zh-CN") : "—") + '</small></div>' +
        (active ? '<button class="btn btn-ghost danger-action" type="button" data-cancel-generation="' + pEsc(job.id) + '">取消</button>' : '') +
      '</div>' +
      (active
        ? '<div class="generation-progress"><div><span>正在生成</span><b>' + progress + '%</b></div><i style="width:' + progress + '%"></i></div>'
        : "") +
      (job.error ? '<p class="generation-error">' + pEsc(job.error) + '</p>' : "") +
      (shots.length ? '<div class="generation-shot-grid">' + shots.map(generationShotMarkup).join("") + '</div>' : "") +
    '</article>'
  );
}

async function loadGenerationCapabilities() {
  const box = p$("#generation-capability");
  const providerLabel = p$("#generation-provider");
  if (!box) return;
  const capability = await pApi("/api/generation/capabilities");
  if (providerLabel) providerLabel.textContent = capability.label || capability.provider;
  box.innerHTML =
    '<div class="generation-capability-row"><span class="generation-provider-badge">' + pEsc(capability.label || capability.provider) + '</span>' +
      '<span class="generation-state ' + (capability.ready ? "is-ready" : "is-blocked") + '">' +
        (capability.ready ? "READY" : "NOT CONNECTED") + '</span></div>' +
    '<p>' + (capability.ready
      ? "平台由服务端配置，浏览器不会传输第三方密钥。Mock 输出仅用于验证分析到生成的产品流程。"
      : pEsc(capability.reason || "当前生成平台尚未接入。")) + '</p>';
  const start = p$("[data-start-generation]");
  if (start) {
    start.disabled = !capability.ready;
    start.title = capability.ready ? "" : (capability.reason || "平台尚未接入");
  }
}

async function loadGenerationJobs(projectId) {
  const box = p$("#prompt-generation-jobs");
  if (!box) return;
  const jobs = await pApi("/api/prompt-projects/" + projectId + "/generation-jobs");
  box.innerHTML = jobs.length
    ? jobs.map(generationJobMarkup).join("")
    : '<p class="muted">还没有视频生成任务。可生成全部镜头，或在单个分镜上点击“生成视频”。</p>';
  stopGenerationPolling();
  if (jobs.some((job) => ["queued", "running"].includes(job.status))) {
    promptState.generationTimer = setTimeout(() => {
      if (promptState.currentId === projectId) {
        loadGenerationJobs(projectId).catch((error) => pToast(error.message));
      }
    }, 1500);
  }
}

async function startGeneration(projectId, shotIndices) {
  const plan = (promptState.currentProject || {}).plan || {};
  const job = await pApi("/api/prompt-projects/" + projectId + "/generation-jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      shot_indices: shotIndices,
      aspect_ratio: plan.aspect_ratio || "",
      model: "",
    }),
  });
  pToast(job.reused ? "已复用相同请求的生成任务" : "视频生成任务已创建");
  await loadGenerationJobs(projectId);
}

async function cancelGenerationTask(jobId, projectId) {
  if (!confirm("确定取消这个视频生成任务？已生成的结果会保留。")) return;
  try {
    await pApi("/api/generation-jobs/" + jobId + "/cancel", { method: "POST" });
    await loadGenerationJobs(projectId);
    pToast("视频生成任务已取消");
  } catch (error) {
    pToast(error.message);
  }
}

async function applyTemplate(projectId, templateId, mode) {
  const fields = mode === "full"
    ? ["shot_type", "camera_movement", "lighting", "color_palette", "transition", "prompt", "negative_prompt", "remake_notes"]
    : ["shot_type", "camera_movement", "lighting", "color_palette", "transition"];
  try {
    const project = await pApi("/api/prompt-projects/" + projectId + "/apply-template", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ template_id: Number(templateId), fields }),
    });
    renderPromptDetail(project);
    await loadPromptAuxiliary(project);
    pToast(mode === "full" ? "模板已套用，含 Prompt 与备注" : "模板风格已套用");
  } catch (error) {
    pToast(error.message);
  }
}

async function deleteTemplate(templateId) {
  if (!confirm("确定删除这个模板？已套用的镜头不会回滚。")) return;
  try {
    await pApi("/api/shot-templates/" + templateId, { method: "DELETE" });
    pToast("模板已删除");
    await loadPromptTemplates();
  } catch (error) {
    pToast(error.message);
  }
}

window.refreshShotTemplates = () => {
  if (p$("#prompt-templates")) {
    loadPromptTemplates().catch((error) => pToast(error.message));
  }
};

async function loadPromptAuxiliary(project) {
  if (!project || project.status !== "done") return;
  const tasks = [
    loadPromptVersions(project.id),
    loadPromptReviews(project.id),
    loadPromptShares(project.id),
    loadPromptCost(project.id),
    loadPromptTemplates(),
    loadGenerationCapabilities(),
    loadGenerationJobs(project.id),
  ];
  if (project.reference) tasks.push(loadPromptComparison(project.id));
  await Promise.all(tasks);
}

function parseEntityItems(value) {
  return String(value || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [name, description = "", appearance = "", mustKeep = ""] = line
        .split("|")
        .map((part) => part.trim());
      return {
        name,
        description,
        appearance,
        must_keep: mustKeep.split(/[；;]/).map((item) => item.trim()).filter(Boolean),
      };
    })
    .filter((item) => item.name);
}

function collectEntityBible(form) {
  const data = new FormData(form);
  return {
    characters: parseEntityItems(data.get("characters")),
    products: parseEntityItems(data.get("products")),
    wardrobe: parseEntityItems(data.get("wardrobe")),
    scenes: parseEntityItems(data.get("scenes")),
    consistency_rules: String(data.get("consistency_rules") || "")
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean),
  };
}

async function savePromptShot(form) {
  const projectId = form.dataset.projectId;
  const shotIndex = form.dataset.shotIndex;
  const data = new FormData(form);
  const payload = {};
  for (const field of ["shot_type", "camera_movement", "subject", "action", "scene", "lighting", "transition", "prompt", "negative_prompt", "remake_notes"]) {
    payload[field] = String(data.get(field) || "");
  }
  payload.color_palette = String(data.get("color_palette") || "")
    .split(/[,，]/)
    .map((item) => item.trim())
    .filter(Boolean);
  payload.locked_fields = data.getAll("locked_fields").map(String);
  const button = form.querySelector('button[type="submit"]');
  if (button) button.disabled = true;
  try {
    const project = await pApi(
      "/api/prompt-projects/" + projectId + "/shots/" + shotIndex,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }
    );
    renderPromptDetail(project);
    await loadPromptAuxiliary(project);
    pToast("镜头已保存，并生成版本快照");
  } catch (error) {
    pToast(error.message);
  } finally {
    if (button) button.disabled = false;
  }
}

async function regeneratePromptShot(projectId, shotIndex) {
  try {
    const project = await pApi(
      "/api/prompt-projects/" + projectId + "/shots/" + shotIndex + "/regenerate",
      { method: "POST" }
    );
    renderPromptDetail(project);
    await loadPromptAuxiliary(project);
    pToast("镜头 " + String(shotIndex).padStart(2, "0") + " 已重生成");
  } catch (error) {
    pToast(error.message);
  }
}

async function restorePromptVersion(projectId, versionId) {
  try {
    const project = await pApi(
      "/api/prompt-projects/" + projectId + "/versions/" + versionId + "/restore",
      { method: "POST" }
    );
    renderPromptDetail(project);
    await loadPromptAuxiliary(project);
    pToast("版本已恢复，并保留恢复前快照");
  } catch (error) {
    pToast(error.message);
  }
}

async function saveEntityBible(form) {
  const projectId = form.dataset.projectId;
  const button = form.querySelector('button[type="submit"]');
  if (button) button.disabled = true;
  try {
    const project = await pApi(
      "/api/prompt-projects/" + projectId + "/entity-bible",
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(collectEntityBible(form)),
      }
    );
    renderPromptDetail(project);
    await loadPromptAuxiliary(project);
    pToast("Entity Bible 已保存，下一次生成或重生成会使用最新设定");
  } catch (error) {
    pToast(error.message);
  } finally {
    if (button) button.disabled = false;
  }
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

async function cancelPromptProject(id) {
  if (!confirm("确定取消当前生成任务？已完成的版本仍会保留。")) return;
  try {
    await pApi("/api/prompt-projects/" + id + "/cancel", { method: "POST" });
    stopPromptPolling();
    stopPromptStream();
    await openPromptProject(id);
    pToast("生成任务已取消");
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
      stopPromptStream();
      stopGenerationPolling();
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
  p$("#prompt-reference").addEventListener("change", async () => {
    try {
      const data = await loadReferenceContext();
      if (data) applyReferenceSuggestions(data);
    } catch (error) {
      pToast(error.message);
    }
  });
  p$("#reference-preview").addEventListener("click", (event) => {
    if (!event.target.closest("[data-clear-reference]")) return;
    const select = p$("#prompt-reference");
    if (select) select.value = "";
    promptState.referenceContext = null;
    renderReferencePreview(null);
  });
  p$("#prompt-refresh").addEventListener("click", () => {
    loadPromptProjects().catch((error) => pToast(error.message));
  });
  p$("#prompt-projects").addEventListener("click", (event) => {
    const item = event.target.closest("[data-prompt-id]");
    if (item) openPromptProject(item.dataset.promptId);
  });
  p$("#prompt-detail").addEventListener("click", async (event) => {
    const editShot = event.target.closest("[data-edit-prompt-shot]");
    if (editShot) {
      const editor = editShot.closest(".story-card")?.querySelector("[data-prompt-shot-editor]");
      if (editor) {
        editor.classList.toggle("hidden");
        if (!editor.classList.contains("hidden")) {
          editor.querySelector("input, textarea")?.focus();
          editor.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
      }
      return;
    }
    const cancelEdit = event.target.closest("[data-cancel-prompt-edit]");
    if (cancelEdit) {
      cancelEdit.closest("[data-prompt-shot-editor]")?.classList.add("hidden");
      return;
    }
    const startGenerationButton = event.target.closest("[data-start-generation]");
    if (startGenerationButton) {
      startGenerationButton.disabled = true;
      startGeneration(startGenerationButton.dataset.startGeneration, [])
        .catch((error) => pToast(error.message))
        .finally(() => { startGenerationButton.disabled = false; });
      return;
    }
    const generateShotButton = event.target.closest("[data-generate-prompt-shot]");
    if (generateShotButton) {
      generateShotButton.disabled = true;
      startGeneration(generateShotButton.dataset.generatePromptShot, [Number(generateShotButton.dataset.shotIndex)])
        .catch((error) => pToast(error.message))
        .finally(() => { generateShotButton.disabled = false; });
      return;
    }
    const cancelGenerationButton = event.target.closest("[data-cancel-generation]");
    if (cancelGenerationButton && promptState.currentId) {
      cancelGenerationTask(cancelGenerationButton.dataset.cancelGeneration, promptState.currentId);
      return;
    }
    const refreshGeneration = event.target.closest("[data-refresh-generation]");
    if (refreshGeneration) {
      loadGenerationJobs(refreshGeneration.dataset.refreshGeneration).catch((error) => pToast(error.message));
      return;
    }
    const applyButton = event.target.closest("[data-apply-template]");
    if (applyButton && promptState.currentId) {
      applyTemplate(
        promptState.currentId,
        applyButton.dataset.applyTemplate,
        applyButton.dataset.applyMode || "style"
      );
      return;
    }
    const deleteTemplateButton = event.target.closest("[data-delete-template]");
    if (deleteTemplateButton) {
      deleteTemplate(deleteTemplateButton.dataset.deleteTemplate);
      return;
    }
    const tagFilter = event.target.closest("[data-template-tag-filter]");
    if (tagFilter) {
      const value = tagFilter.dataset.templateTagFilter || "";
      promptState.selectedTemplateTags = promptState.selectedTemplateTags.includes(value)
        ? promptState.selectedTemplateTags.filter((tag) => tag !== value)
        : [...promptState.selectedTemplateTags, value];
      loadPromptTemplates().catch((error) => pToast(error.message));
      return;
    }
    if (event.target.closest("[data-reset-template-filters]")) {
      promptState.selectedTemplateCategory = "";
      promptState.selectedTemplateTags = [];
      const search = p$("#template-search");
      if (search) search.value = "";
      loadPromptTemplates().catch((error) => pToast(error.message));
      return;
    }
    const cancelPrompt = event.target.closest("[data-cancel-prompt]");
    if (cancelPrompt) {
      cancelPromptProject(cancelPrompt.dataset.cancelPrompt);
      return;
    }
    const regenerateShot = event.target.closest("[data-regenerate-prompt-shot]");
    if (regenerateShot && promptState.currentId) {
      regeneratePromptShot(promptState.currentId, Number(regenerateShot.dataset.shotIndex));
      return;
    }
    const restoreVersion = event.target.closest("[data-restore-version]");
    if (restoreVersion && promptState.currentId) {
      restorePromptVersion(promptState.currentId, restoreVersion.dataset.restoreVersion);
      return;
    }
    const openReference = event.target.closest("[data-open-reference]");
    if (openReference) {
      switchMode("reverse");
      if (typeof openProject === "function") openProject(openReference.dataset.openReference);
      return;
    }
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
    const copyShare = event.target.closest("[data-copy-share]");
    if (copyShare) {
      try {
        const copied = await copyText(copyShare.dataset.copyShare || "");
        pToast(copied ? "分享链接已复制" : "复制失败，请打开链接后手动复制");
      } catch (_) {
        pToast("复制失败，请打开链接后手动复制");
      }
      return;
    }
    const toggleShareQrButton = event.target.closest("[data-toggle-share-qr]");
    if (toggleShareQrButton && promptState.currentId) {
      toggleShareQr(
        promptState.currentId,
        toggleShareQrButton.dataset.toggleShareQr,
        toggleShareQrButton
      );
      return;
    }
    const revokeShareButton = event.target.closest("[data-revoke-share]");
    if (revokeShareButton && promptState.currentId) {
      if (confirm("确定撤销这个分享链接？撤销后访客将无法继续访问。")) {
        await revokeShare(promptState.currentId, revokeShareButton.dataset.revokeShare);
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
  p$("#prompt-detail").addEventListener("input", (event) => {
    if (!event.target.closest("#template-search")) return;
    clearTimeout(promptState.templateTimer);
    promptState.templateTimer = setTimeout(() => {
      loadPromptTemplates().catch((error) => pToast(error.message));
    }, 220);
  });
  p$("#prompt-detail").addEventListener("change", (event) => {
    if (!event.target.closest("#template-category-filter")) return;
    promptState.selectedTemplateCategory = event.target.value;
    loadPromptTemplates().catch((error) => pToast(error.message));
  });
  p$("#prompt-detail").addEventListener("submit", (event) => {
    const shotEditor = event.target.closest("[data-prompt-shot-editor]");
    if (shotEditor) {
      event.preventDefault();
      savePromptShot(shotEditor);
      return;
    }
    const entityForm = event.target.closest("[data-entity-form]");
    if (entityForm) {
      event.preventDefault();
      saveEntityBible(entityForm);
      return;
    }
    const reviewForm = event.target.closest("[data-review-form]");
    if (reviewForm) {
      event.preventDefault();
      submitReview(reviewForm);
      return;
    }
    const compareForm = event.target.closest("[data-version-compare]");
    if (compareForm) {
      event.preventDefault();
      const data = new FormData(compareForm);
      comparePromptVersions(
        compareForm.dataset.projectId,
        data.get("left_id"),
        data.get("right_id")
      );
      return;
    }
    const shareForm = event.target.closest("[data-share-form]");
    if (shareForm) {
      event.preventDefault();
      submitShare(shareForm);
    }
  });

  const initialHash = window.location.hash;
  if (initialHash === "#generate" || initialHash === "#generate-view") {
    switchMode("generate", false);
  } else if (initialHash === "#quality" || initialHash === "#quality-view") {
    switchMode("quality", false);
  }
  loadReferenceProjects().catch((error) => pToast(error.message));
  window.addEventListener("hashchange", () => {
    if (window.location.hash === "#generate" || window.location.hash === "#generate-view") {
      switchMode("generate", false);
    } else if (window.location.hash === "#quality" || window.location.hash === "#quality-view") {
      switchMode("quality", false);
    } else if (window.location.hash === "#reverse" || window.location.hash === "#reverse-view") {
      switchMode("reverse", false);
    }
  });
});
