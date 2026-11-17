/**
 * DEMONSTRATION DATA. Nothing in this file was recorded from a real user or a real session.
 * Illustrative series are shaped around the validation figures in ./benchmarks so charts read
 * correctly; every UI that renders them must show a "Demonstration data" or "Illustrative" label.
 */
import type { EmotionId } from "./emotions";
import { VALIDATION } from "./benchmarks";

function rng(seed: number) {
  let s = seed;
  return () => ((s = (s * 16807) % 2147483647) / 2147483647);
}

export interface DemoSession {
  id: string;
  name: string;
  avatar: string;
  input: "Microphone" | "Audio file" | "Text-to-speech";
  emotion: EmotionId;
  intensity: number;
  durationS: number;
  createdAt: string; // ISO date
  status: "Complete" | "Exported" | "Interrupted";
}

export const DEMO_SESSIONS: DemoSession[] = [
  { id: "demo-01", name: "Lecture intro take 1", avatar: "Demo portrait A", input: "Microphone", emotion: "neutral", intensity: 40, durationS: 74, createdAt: "2026-11-02", status: "Exported" },
  { id: "demo-02", name: "Greeting — warm", avatar: "Demo portrait A", input: "Microphone", emotion: "happy", intensity: 70, durationS: 22, createdAt: "2026-11-03", status: "Complete" },
  { id: "demo-03", name: "Emotion sweep", avatar: "Demo portrait B", input: "Microphone", emotion: "surprised", intensity: 85, durationS: 48, createdAt: "2026-11-05", status: "Complete" },
  { id: "demo-04", name: "Network drop test", avatar: "Demo portrait B", input: "Microphone", emotion: "sad", intensity: 55, durationS: 31, createdAt: "2026-11-07", status: "Interrupted" },
  { id: "demo-05", name: "Narration draft", avatar: "Demo portrait C", input: "Audio file", emotion: "neutral", intensity: 20, durationS: 126, createdAt: "2026-11-09", status: "Complete" },
  { id: "demo-06", name: "Firm tone check", avatar: "Demo portrait C", input: "Microphone", emotion: "angry", intensity: 60, durationS: 19, createdAt: "2026-11-11", status: "Exported" },
  { id: "demo-07", name: "Scripted welcome", avatar: "Demo portrait A", input: "Text-to-speech", emotion: "happy", intensity: 50, durationS: 15, createdAt: "2026-11-12", status: "Complete" },
];

/** Illustrative FPS trace over a 60 s run, centred on the reported ≈25 FPS. */
export const ILLUSTRATIVE_FPS = (() => {
  const r = rng(42);
  return Array.from({ length: 60 }, (_, i) => ({
    t: i,
    fps: Math.round((VALIDATION.fps + (r() - 0.5) * 1.6 - (i === 0 ? 4 : 0)) * 10) / 10,
  }));
})();

/** Illustrative latency histogram shaped so p50 ≈ 269 ms and p95 ≈ 319 ms. */
export const ILLUSTRATIVE_LATENCY = (() => {
  const bins: { bin: string; count: number; lo: number }[] = [];
  for (let lo = 230; lo <= 350; lo += 10) {
    const mid = lo + 5;
    const z = mid < 269 ? (mid - 269) / 16 : (mid - 269) / 30;
    bins.push({ bin: `${lo}`, lo, count: Math.round(400 * Math.exp(-0.5 * z * z)) });
  }
  return bins;
})();

/** Illustrative per-second frame delivery for 40 s (25 expected). */
export const ILLUSTRATIVE_DELIVERY = (() => {
  const r = rng(7);
  return Array.from({ length: 40 }, (_, i) => {
    const dropped = r() > 0.88 ? Math.ceil(r() * 2) : 0;
    return { t: i, delivered: 25 - dropped, dropped };
  });
})();

/**
 * Illustrative 5-class confusion matrix (rows = true, cols = predicted), row-normalised.
 * Constructed so macro-F1 ≈ 0.651. It is NOT the matrix from the validation report.
 */
export const EMOTION_ORDER: EmotionId[] = ["neutral", "happy", "sad", "angry", "surprised"];
export const ILLUSTRATIVE_CONFUSION: number[][] = [
  [0.62, 0.08, 0.14, 0.08, 0.08],
  [0.08, 0.74, 0.04, 0.04, 0.1],
  [0.18, 0.04, 0.6, 0.12, 0.06],
  [0.1, 0.04, 0.12, 0.66, 0.08],
  [0.1, 0.12, 0.06, 0.08, 0.64],
];

export function macroF1(m: number[][]) {
  const n = m.length;
  let total = 0;
  for (let k = 0; k < n; k++) {
    const row = m[k] ?? [];
    const tp = row[k] ?? 0;
    const fn = row.reduce((a, b) => a + b, 0) - tp;
    const fp = m.reduce((a, r) => a + (r[k] ?? 0), 0) - tp;
    const p = tp / (tp + fp);
    const r = tp / (tp + fn);
    total += (2 * p * r) / (p + r);
  }
  return total / n;
}

/** Illustrative intensity distribution across demonstration sessions. */
export const ILLUSTRATIVE_INTENSITY = [
  { band: "0–20", count: 3 },
  { band: "21–40", count: 6 },
  { band: "41–60", count: 9 },
  { band: "61–80", count: 7 },
  { band: "81–100", count: 4 },
];
