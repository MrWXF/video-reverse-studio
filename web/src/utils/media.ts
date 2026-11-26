export function readVideoDuration(file: File): Promise<number> {
  return new Promise((resolve) => {
    const video = document.createElement("video");
    const url = URL.createObjectURL(file);
    let settled = false;
    let timer: number | null = null;

    const finish = (value: number) => {
      if (settled) {
        return;
      }
      settled = true;
      if (timer !== null) {
        window.clearTimeout(timer);
      }
      video.removeAttribute("src");
      video.load();
      URL.revokeObjectURL(url);
      resolve(value);
    };

    timer = window.setTimeout(() => finish(0), 6000);
    video.preload = "metadata";
    video.onloadedmetadata = () => {
      const duration = Number(video.duration);
      finish(Number.isFinite(duration) && duration > 0 ? duration : 0);
    };
    video.onerror = () => finish(0);
    video.src = url;
  });
}
