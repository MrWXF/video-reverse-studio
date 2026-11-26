import { create } from "zustand";

export type ThemeStyle = "a" | "b";

interface ToastState {
  message: string;
  tone: "default" | "success" | "error";
}

interface UiState {
  style: ThemeStyle;
  toast: ToastState | null;
  setStyle: (style: ThemeStyle) => void;
  showToast: (message: string, tone?: ToastState["tone"]) => void;
  clearToast: () => void;
}

function readInitialStyle(): ThemeStyle {
  try {
    const requested = new URLSearchParams(window.location.search).get("style");
    if (requested === "a" || requested === "b") {
      return requested;
    }
    return localStorage.getItem("reelreverse-style") === "b" ? "b" : "a";
  } catch {
    return "a";
  }
}

function applyStyle(style: ThemeStyle): void {
  document.documentElement.dataset.style = style;
  try {
    localStorage.setItem("reelreverse-style", style);
  } catch {
    // Theme persistence is optional in restricted browser contexts.
  }
}

export const useUiStore = create<UiState>((set) => ({
  style: readInitialStyle(),
  toast: null,
  setStyle: (style) => {
    applyStyle(style);
    set({ style });
  },
  showToast: (message, tone = "default") => set({ toast: { message, tone } }),
  clearToast: () => set({ toast: null }),
}));
