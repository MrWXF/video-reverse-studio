(() => {
  const toast = document.querySelector("#toast");
  let toastTimer;

  function showToast(message) {
    if (!toast || !message) return;
    toast.textContent = message;
    toast.classList.add("is-visible");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => {
      toast.classList.remove("is-visible");
    }, 2800);
  }

  async function copyText(text) {
    if (!text) return false;
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (error) {
      const helper = document.createElement("textarea");
      helper.value = text;
      helper.setAttribute("readonly", "");
      helper.style.position = "fixed";
      helper.style.opacity = "0";
      document.body.appendChild(helper);
      helper.select();
      const copied = document.execCommand("copy");
      helper.remove();
      return copied;
    }
  }

  const modeButtons = Array.from(document.querySelectorAll("[data-mode]"));
  const modePanels = Array.from(document.querySelectorAll("[data-panel]"));

  modeButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const mode = button.dataset.mode;
      modeButtons.forEach((item) => {
        const active = item === button;
        item.classList.toggle("is-active", active);
        item.setAttribute("aria-selected", String(active));
      });
      modePanels.forEach((panel) => {
        panel.classList.toggle("is-active", panel.dataset.panel === mode);
      });
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });

  const requestedMode = window.location.hash.replace("#", "");
  if (requestedMode === "reverse" || requestedMode === "generate") {
    const requestedButton = modeButtons.find((button) => button.dataset.mode === requestedMode);
    if (requestedButton && !requestedButton.classList.contains("is-active")) {
      requestedButton.click();
    }
  }

  document.querySelectorAll("[data-collapse]").forEach((button) => {
    button.addEventListener("click", () => {
      const card = button.closest(".result-card");
      if (!card) return;
      const collapsed = card.classList.toggle("is-collapsed");
      button.setAttribute("aria-expanded", String(!collapsed));
    });
  });

  const expandAll = document.querySelector("[data-expand-all]");

  function syncExpandAll() {
    if (!expandAll) return;
    const cards = Array.from(document.querySelectorAll(".shot-list .result-card"));
    if (!cards.length) return;
    const allOpen = cards.every((card) => !card.classList.contains("is-collapsed"));
    expandAll.textContent = allOpen ? "全部收起" : "全部展开";
  }

  if (expandAll) {
    expandAll.addEventListener("click", () => {
      const cards = Array.from(document.querySelectorAll(".shot-list .result-card"));
      const allOpen = cards.every((card) => !card.classList.contains("is-collapsed"));
      cards.forEach((card) => {
        card.classList.toggle("is-collapsed", allOpen);
        const button = card.querySelector("[data-collapse]");
        if (button) button.setAttribute("aria-expanded", String(allOpen ? false : true));
      });
      syncExpandAll();
    });
    syncExpandAll();
  }

  document.querySelectorAll(".project-item").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".project-item").forEach((item) => item.classList.remove("is-selected"));
      button.classList.add("is-selected");
      const title = document.querySelector("#project-title");
      const meta = document.querySelector("#project-meta");
      if (title) title.textContent = button.dataset.project || title.textContent;
      if (meta) meta.textContent = button.dataset.meta || meta.textContent;
      showToast(`已切换到「${button.dataset.project || "项目"}」`);
    });
  });

  document.querySelectorAll("[data-copy-text]").forEach((button) => {
    button.addEventListener("click", async () => {
      const copied = await copyText(button.dataset.copyText);
      showToast(copied ? "Prompt 已复制到剪贴板" : "复制失败，请手动选择文本");
    });
  });

  document.querySelectorAll(".chip-row").forEach((row) => {
    const single = row.hasAttribute("data-single");
    row.querySelectorAll(".chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        if (single) {
          row.querySelectorAll(".chip").forEach((item) => item.classList.remove("is-active"));
          chip.classList.add("is-active");
        } else {
          chip.classList.toggle("is-active");
        }
      });
    });
  });

  document.querySelectorAll("[data-segment]").forEach((group) => {
    group.querySelectorAll("button").forEach((button) => {
      button.addEventListener("click", () => {
        group.querySelectorAll("button").forEach((item) => item.classList.remove("is-active"));
        button.classList.add("is-active");
      });
    });
  });

  document.querySelectorAll("[data-toast]").forEach((button) => {
    button.addEventListener("click", () => showToast(button.dataset.toast));
  });

  const generate = document.querySelector("[data-generate]");
  if (generate) {
    generate.addEventListener("click", () => {
      const label = generate.innerHTML;
      generate.disabled = true;
      generate.style.opacity = "0.72";
      generate.textContent = "正在生成分镜…";
      window.setTimeout(() => {
        generate.disabled = false;
        generate.style.opacity = "";
        generate.innerHTML = label;
        showToast("演示完成：已生成 4 个镜头与中英双语 Prompt");
        const storyboard = document.querySelector("#storyboard");
        if (storyboard) storyboard.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 900);
    });
  }
})();