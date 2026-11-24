(function (global) {
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
        /* non-JSON error response */
      }
      throw new Error(detail);
    }
    return response.json();
  }

  async function copyText(text) {
    if (!text) return false;
    if (navigator.clipboard && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(text);
        return true;
      } catch (_) {
        /* fall through to execCommand */
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

  global.ReelReverse = {
    $,
    esc,
    toast,
    api,
    copyText,
    formatNumber,
    formatClock,
  };
})(window);
