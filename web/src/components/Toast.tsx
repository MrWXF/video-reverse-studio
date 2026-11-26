import { useEffect } from "react";

import { useUiStore } from "../store/uiStore";

export function Toast() {
  const toast = useUiStore((state) => state.toast);
  const clearToast = useUiStore((state) => state.clearToast);

  useEffect(() => {
    if (!toast) {
      return undefined;
    }
    const timer = window.setTimeout(clearToast, 3600);
    return () => window.clearTimeout(timer);
  }, [toast, clearToast]);

  return (
    <div
      className={`toast${toast ? "" : " hidden"}${toast?.tone === "error" ? " is-error" : ""}`}
      role="status"
      aria-live="polite"
    >
      {toast?.message ?? ""}
    </div>
  );
}
