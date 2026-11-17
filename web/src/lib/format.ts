/** 00:00:04:12 style timecode at 25 fps. */
export function timecode(ms: number, fps = 25) {
  const total = Math.max(0, ms);
  const s = Math.floor(total / 1000);
  const f = Math.floor(((total % 1000) / 1000) * fps);
  const hh = Math.floor(s / 3600);
  const mm = Math.floor((s % 3600) / 60);
  const ss = s % 60;
  return [hh, mm, ss, f].map((n) => String(n).padStart(2, "0")).join(":");
}

export function duration(ms: number) {
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function frameNo(n: number) {
  return String(Math.max(0, Math.floor(n))).padStart(6, "0");
}
