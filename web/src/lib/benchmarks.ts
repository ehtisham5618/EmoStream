/**
 * Validation figures supplied for EmoStream. These are the ONLY performance numbers
 * the interface may present as measured. Anything else must be labelled illustrative.
 */
export const VALIDATION = {
  resolution: "512×512",
  fps: 25,
  fpsHardware: "NVIDIA L40S · TensorRT",
  peakVramGiB: 2.77,
  serverP50Ms: 269,
  serverP95Ms: 319,
  arcface: 0.93,
  emotionMacroF1: 0.651,
} as const;

export const DISCLAIMER =
  "These are validation measurements from specific experimental configurations. Performance varies by GPU, network, browser and workload. RTX 4050 performance has not yet been verified.";

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
    note: "TensorRT engine, 512×512 output. Source of the headline figures.",
    fps: "≈25",
    vram: "2.77 GiB",
    p50: "269 ms",
    p95: "319 ms",
  },
  {
    gpu: "NVIDIA A10G",
    status: "tested",
    note: "Included in validation runs. Figures are not published in this build.",
  },
  {
    gpu: "NVIDIA RTX 4050 (laptop)",
    status: "unverified",
    note: "Not yet verified. No performance claim is made for this GPU.",
  },
];

export const MODEL = {
  name: "EmoStream BehaviourNet",
  params: "1.36M",
  facts: [
    "Causal — predicts motion from past and present audio only, so it can stream.",
    "Separate articulation and emotion branches.",
    "Trained on MEAD (multi-view emotional audio-visual dataset).",
  ],
  renderer: "Frozen LivePortrait, Ditto-packaged implementation",
  audioEncoder: "HuBERT",
} as const;
