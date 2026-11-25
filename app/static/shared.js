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

  function formatCost(cost) {
    if (!cost || !cost.priced || cost.estimated_cost === null || cost.estimated_cost === undefined) {
      return "未配置单价";
    }
    const value = Number(cost.estimated_cost || 0);
    const digits = value > 0 && value < 0.01 ? 6 : 4;
    return (cost.currency || "USD") + " " + value.toFixed(digits);
  }

  function usageMarkup(usage, compact = false) {
    if (!usage) return "";
    const cost = usage.cost || {};
    return (
      '<div class="usage-strip' + (compact ? " is-compact" : "") + '">' +
        '<div class="usage-metric"><span>CALLS</span><strong>' + esc(formatNumber(cost.calls, 0)) + '</strong></div>' +
        '<div class="usage-metric"><span>INPUT</span><strong>' + esc(formatNumber(cost.prompt_tokens, 0)) + '</strong><small>tokens</small></div>' +
        '<div class="usage-metric"><span>OUTPUT</span><strong>' + esc(formatNumber(cost.completion_tokens, 0)) + '</strong><small>tokens</small></div>' +
        '<div class="usage-metric is-cost"><span>EST. COST</span><strong>' + esc(formatCost(cost)) + '</strong><small>' + esc(cost.note || "估算值") + '</small></div>' +
      '</div>'
    );
  }

  global.ReelReverse = {
    $,
    esc,
    toast,
    api,
    copyText,
    formatNumber,
    formatClock,
    formatCost,
    usageMarkup,
  };
})(window);
