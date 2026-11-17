/**
 * Measured figures for EmoStream. These are the ONLY performance and quality numbers the
 * interface may present as measured. Each one names its model, date, hardware and source report
 * in this repository. Anything else must be labelled illustrative or left empty.
 */

/**
 * HISTORICAL: validation of the first trained behaviour model `reg` (HuBERT speech features,
 * block streaming), 15 Nov 2026. Source: docs/evaluation/2026-11-15_validation_report.md.
 * Server-side engine figures from a five-minute run on an NVIDIA L40S (TensorRT fp16).
 * Not the model that is live now; see CURRENT.
 */
export const VALIDATION = {
  model: "reg",
  date: "15 Nov 2026",
  source: "docs/evaluation/2026-11-15_validation_report.md",
  resolution: "512×512",
  fps: 25,
  fpsHardware: "NVIDIA L40S · TensorRT",
  peakVramGiB: 2.77,
  serverP50Ms: 269,
  serverP95Ms: 319,
  arcface: 0.93,
  emotionMacroF1: 0.651,
} as const;

/**
 * CURRENT: the live model `ph_aug` (WavLM-base-plus layer-6 speech features, trained half the
 * time on degraded "real microphone" audio), 17 Nov 2026.
 * Quality: 80 MEAD validation clips rendered per-frame (A10G), validation actors only.
 * Live: deployed worker (L40S, TensorRT), headless Chromium, the user's recording as microphone.
 * Sources: docs/iterations/current_iteration/final_articulation_report.md and
 * articulation_model_experiments.md; docs/evaluation/data/browser_l40s_final_ph_aug.json.
 */
export const CURRENT = {
  model: "ph_aug",
  date: "17 Nov 2026",
  lseC: 5.08,
  lseD: 9.15,
  realLseC: 5.78,
  realLseD: 8.69,
  mouthOpenCorr: 0.6,
  emotionMacroF1: 0.777,
  arcface: 0.876,
  bilabialPrecision: 0.72,
  liveFramesSkipped: 1,
  liveFramesTotal: 688,
  liveDrawnFps: 23.6,
  liveVoiceWithin80: 0.93,
  liveServerP50Ms: 209,
} as const;

/** Validation history, 80 MEAD validation clips rendered (same evaluation for every row). */
export const MODEL_HISTORY: { model: string; note: string; lseC?: number; lseD?: number; mouthCorr: number; f1?: number; arcface?: number }[] = [
  { model: "reg", note: "HuBERT, block streaming · 15 Nov", mouthCorr: 0.52 },
  { model: "it_ccc_la2", note: "HuBERT, concordance loss, look-ahead · 16 Nov", lseC: 4.89, lseD: 9.43, mouthCorr: 0.546, f1: 0.77, arcface: 0.882 },
  { model: "wl_base", note: "WavLM layer 6 · 17 Nov", lseC: 4.74, lseD: 9.55, mouthCorr: 0.582, f1: 0.84, arcface: 0.882 },
  { model: "ph_aug", note: "WavLM + degraded-audio training · live", lseC: 5.08, lseD: 9.15, mouthCorr: 0.6, f1: 0.78, arcface: 0.876 },
];

export const DISCLAIMER =
  "These are measurements from specific experimental configurations, each labelled with its model and date. Performance varies by GPU, network, browser and workload. RTX 4050 performance has not yet been verified.";

export const LATENCY_NOTE =
  "Server-side latency only. It excludes network transit, browser decoding and display, so what a viewer experiences is higher.";

export type HardwareStatus = "measured" | "tested" | "unverified";

export const HARDWARE: {
  gpu: string;
  status: HardwareStatus;
  note: string;
  fps?: string;
  vram?: string;
  p50?: string;
  p95?: string;
}[] = [
  {
    gpu: "NVIDIA L40S",
    status: "measured",
    note: "TensorRT engine, 512×512 output. Engine figures from the 15 Nov validation run (model reg); the live worker runs here.",
    fps: "≈25",
    vram: "2.77 GiB",
    p50: "269 ms",
    p95: "319 ms",
  },
  {
    gpu: "NVIDIA A10G",
    status: "tested",
    note: "Used for offline evaluation renders. Too slow for per-frame live streaming with the WavLM model.",
  },
  {
    gpu: "NVIDIA RTX 4050 (laptop)",
    status: "unverified",
    note: "Not yet verified. No performance claim is made for this GPU.",
  },
];

export const MODEL = {
  name: "EmoStream BehaviourNet",
  /** From the architecture at WavLM's 768-d input; the engine reports the exact count in /api/info. */
  params: "≈1.30M",
  facts: [
    "Causal: predicts motion from past and present audio plus 80 ms of look-ahead, so it can stream.",
    "Separate articulation and emotion branches.",
    "Trained on MEAD (multi-view emotional audio-visual dataset), half the time on degraded microphone-like audio.",
  ],
  renderer: "Frozen LivePortrait, Ditto-packaged implementation",
  audioEncoder: "WavLM-base-plus (layer 6)",
} as const;
