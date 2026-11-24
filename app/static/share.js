const shareApp = document.getElementById("share-app");
const token = document.body.dataset.token;
const permission = document.body.dataset.permission || "read";

function sEsc(value) {
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

function sClock(value) {
  const total = Math.max(0, Number(value || 0));
  const minutes = Math.floor(total / 60);
  const seconds = total - minutes * 60;
  return String(minutes).padStart(2, "0") + ":" + seconds.toFixed(1).padStart(4, "0");
}

async function shareApi(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch (_) {
      /* ignore */
    }
    throw new Error(detail);
  }
  return response.json();
}

function palette(colors) {
  return (colors || []).filter(Boolean).map((color) => '<i style="background:' + sEsc(color) + '"></i>').join("");
}

function shotMarkup(shot) {
  const paletteMarkup = palette(shot.color_palette);
  return (
    '<article class="share-shot"><div class="share-shot-head"><span>SHOT ' + sEsc(String(shot.index).padStart(2, "0")) + '</span>' +
      '<small>' + sEsc(sClock(shot.start_s)) + ' — ' + sEsc(sClock(shot.end_s)) + '</small></div>' +
      '<h3>' + sEsc(shot.subject || "未命名镜头") + '</h3>' +
      '<p class="share-shot-scene">' + sEsc([shot.action, shot.scene].filter(Boolean).join(" · ") || "场景描述待补充") + '</p>' +
      '<div class="share-shot-tags"><span>' + sEsc(shot.shot_type || "—") + '</span><span>' + sEsc(shot.camera_movement || "—") + '</span><span>' + sEsc(shot.lighting || "—") + '</span></div>' +
      '<div class="share-prompt"><span>PROMPT</span><p>' + sEsc(shot.prompt || "未生成 Prompt") + '</p></div>' +
      '<div class="share-negative"><b>Negative</b> ' + sEsc(shot.negative_prompt || "—") + '</div>' +
      '<div class="share-palette">' + paletteMarkup + '</div></article>'
  );
}

function renderShare(project) {
  const plan = project.plan || {};
  const shots = plan.shots || [];
  const summary = plan.summary || project.brief?.idea || "共享分镜方案";
  const version = project.version_number ? "V" + String(project.version_number).padStart(2, "0") : "当前版本";
  shareApp.innerHTML =
    '<section class="share-hero"><p class="panel-kicker">SHARED STORYBOARD / ' + sEsc(version) + '</p>' +
      '<h1>' + sEsc(project.title || plan.title || "共享分镜") + '</h1><p>' + sEsc(summary) + '</p>' +
      '<div class="share-meta"><span>' + sEsc(plan.target_model || "generic") + '</span><span>' + sEsc(Number(plan.duration_s || 0).toFixed(1)) + 's</span>' +
      '<span>' + sEsc(plan.aspect_ratio || "—") + '</span><span>' + shots.length + ' shots</span>' +
      '<span>' + sEsc(project.share?.permission === "comment" ? "可评论" : "只读") + '</span></div></section>' +
    '<section class="share-shot-grid">' + shots.map(shotMarkup).join("") + '</section>' +
    '<section class="share-comments"><div class="share-comments-head"><div><span class="panel-kicker">FEEDBACK</span><h2>审阅评论</h2></div>' +
      '<span id="share-comment-count">0</span></div><div id="share-comment-list" class="share-comment-list"><p class="muted">正在加载评论…</p></div>' +
      (permission === "comment"
        ? '<form id="share-comment-form" class="share-comment-form"><label class="field"><span class="field-label">称呼</span><input class="input" name="author" maxlength="80" placeholder="你的名字" /></label>' +
          '<label class="field"><span class="field-label">评论</span><textarea class="textarea" name="content" rows="3" maxlength="2000" placeholder="写下对这一版分镜的意见" required></textarea></label>' +
          '<button class="btn btn-primary" type="submit">提交评论</button></form>'
        : '<p class="share-readonly">该链接为只读分享，未开放评论。</p>') +
    '</section>';
  loadComments();
  const form = document.getElementById("share-comment-form");
  if (form) form.addEventListener("submit", submitComment);
}

async function loadComments() {
  const list = document.getElementById("share-comment-list");
  if (!list) return;
  try {
    const comments = await shareApi("/api/shares/" + token + "/comments");
    const counter = document.getElementById("share-comment-count");
    if (counter) counter.textContent = comments.length + " 条";
    list.innerHTML = comments.length
      ? comments.map((comment) => '<article class="share-comment"><div><strong>' + sEsc(comment.author) + '</strong>' +
          '<small>' + sEsc(new Date(comment.created_at).toLocaleString("zh-CN")) + '</small></div><p>' + sEsc(comment.content) + '</p></article>').join("")
      : '<p class="muted">还没有评论，欢迎留下第一条反馈。</p>';
  } catch (error) {
    list.innerHTML = '<p class="muted">' + sEsc(error.message) + '</p>';
  }
}

async function submitComment(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  const button = form.querySelector('button[type="submit"]');
  if (button) button.disabled = true;
  try {
    await shareApi("/api/shares/" + token + "/comments", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ author: data.get("author") || "访客", content: data.get("content") }),
    });
    form.reset();
    await loadComments();
  } catch (error) {
    alert(error.message);
  } finally {
    if (button) button.disabled = false;
  }
}

shareApi("/api/shares/" + token)
  .then(renderShare)
  .catch((error) => {
    shareApp.innerHTML = '<div class="share-error"><span>!</span><h1>分享链接不可用</h1><p>' + sEsc(error.message) + '</p></div>';
  });
