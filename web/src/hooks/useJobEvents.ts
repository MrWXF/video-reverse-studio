import { useEffect, useRef } from "react";

export function useJobEvents(jobId: string | null | undefined, enabled: boolean, onEvent: () => void): void {
  const callbackRef = useRef(onEvent);
  callbackRef.current = onEvent;

  useEffect(() => {
    if (!enabled || !jobId || typeof EventSource === "undefined") {
      return undefined;
    }

    let failures = 0;
    let pollTimer: number | null = null;
    const stream = new EventSource(`/api/jobs/${encodeURIComponent(jobId)}/events`);

    const startPolling = () => {
      if (pollTimer !== null) {
        return;
      }
      pollTimer = window.setInterval(() => callbackRef.current(), 1800);
    };

    const onProgress = () => callbackRef.current();
    const onComplete = () => {
      stream.close();
      callbackRef.current();
    };
    const onError = () => {
      failures += 1;
      if (failures >= 2) {
        stream.close();
        startPolling();
      }
    };

    stream.addEventListener("open", () => {
      failures = 0;
    });
    stream.addEventListener("progress", onProgress);
    stream.addEventListener("complete", onComplete);
    stream.addEventListener("error", onError);

    return () => {
      stream.close();
      if (pollTimer !== null) {
        window.clearInterval(pollTimer);
      }
    };
  }, [enabled, jobId]);
}
