import type { CSSProperties } from "react";
import { createStore, useStore } from "./store";
import { settingsStore } from "./settings";
import type { EmotionId } from "./emotions";

export interface Crop {
  x: number; // -1..1 pan
  y: number;
  zoom: number; // 1..3
}

export type FaceCheck = "pending" | "found" | "not-found" | "unsupported" | "multiple";

export interface Portrait {
  url: string;
  name: string;
  type: string;
  sizeBytes: number;
  width: number;
  height: number;
  crop: Crop;
  faceCheck: FaceCheck;
  addedAt: number;
}

export interface SessionSummary {
  id: string;
  avatarName: string;
  startedAt: number;
  durationMs: number;
  emotionChanges: number;
  finalEmotion: EmotionId;
  finalIntensity: number;
  engine: boolean;
  framesReceived: number;
  /** How the take ended. */
  outcome: "complete" | "lost" | "error";
  exported: boolean;
  /** Measured in this browser, one value per second: pictures drawn per second (on screen). */
  fpsPerSecond: number[];
  /** Frames received per second, and frames lost per second (skipped by the engine or the network, or late here). */
  deliveredPerSecond: number[];
  droppedPerSecond: number[];
  /** Server-side audio-to-frame latency of each received frame (from the video frame header), ms. */
  latencyMs: number[];
  /** Intensity (0–100) of each emotion setting used in the take. */
  intensities: number[];
}

export interface StudioState {
  portrait: Portrait | null;
  avatarName: string;
  /** Portrait consent: the user may use this portrait and the person shown agreed to animation. */
  consent: boolean;
  /** Voice consent: the user agrees to their microphone audio being sent to the engine. */
  voiceConsent: boolean;
  emotion: EmotionId;
  intensity: number;
  /** Sessions run in this browser tab. The engine does not persist history. */
  sessions: SessionSummary[];
}

const s = settingsStore.get();

const INITIAL: StudioState = {
  portrait: null,
  avatarName: "Untitled avatar",
  consent: false,
  voiceConsent: false,
  emotion: s.defaultEmotion,
  intensity: s.defaultIntensity,
  sessions: [],
};

export const studioStore = createStore<StudioState>(INITIAL);

export function useStudio<S>(selector: (s: StudioState) => S): S {
  return useStore(studioStore, selector, INITIAL);
}

export const PORTRAIT_RULES = {
  types: ["image/jpeg", "image/png", "image/webp"],
  maxBytes: 10 * 1024 * 1024,
  minSide: 256,
  recommendedSide: 512,
};

export function validatePortraitFile(file: { type: string; size: number }): string | null {
  if (!PORTRAIT_RULES.types.includes(file.type)) return "Use a JPG, PNG or WebP image.";
  if (file.size > PORTRAIT_RULES.maxBytes)
    return "That image is over 10 MB. Export a smaller copy and try again.";
  return null;
}

export function validatePortraitSize(w: number, h: number): string | null {
  if (Math.min(w, h) < PORTRAIT_RULES.minSide)
    return `This image is ${w}×${h}. Portraits need at least ${PORTRAIT_RULES.minSide}px on the short side.`;
  return null;
}

/** Can a session start? Portrait present, both consents given, face not rejected. */
export function canStartSession(st: Pick<StudioState, "portrait" | "consent" | "voiceConsent">) {
  if (!st.portrait) return { ok: false, reason: "Upload a portrait to create your avatar." };
  if (!st.consent) return { ok: false, reason: "Confirm consent for this portrait first." };
  if (!st.voiceConsent)
    return { ok: false, reason: "Confirm consent for sending your voice to the engine." };
  if (st.portrait.faceCheck === "not-found")
    return { ok: false, reason: "No face was found. Try a clearer, front-facing photo." };
  if (st.portrait.faceCheck === "multiple")
    return { ok: false, reason: "More than one face found. Use a portrait of one person." };
  return { ok: true as const, reason: "" };
}

/**
 * The cropped square as JPEG bytes, sent to the engine as the portrait (binary 0x10 message).
 * Rendered at the source's own resolution up to `maxSize` (never upscaled), so the engine's face
 * detection sees as much detail as the upload has. The engine output frames show this square.
 */
export async function renderCropJpeg(p: Portrait, maxSize = 1024): Promise<ArrayBuffer> {
  const img = await loadImage(p.url);
  const side = Math.min(img.width, img.height) / p.crop.zoom;
  const size = Math.max(PORTRAIT_RULES.minSide, Math.min(maxSize, Math.round(side)));
  const c = document.createElement("canvas");
  c.width = size;
  c.height = size;
  const ctx = c.getContext("2d")!;
  const maxX = (img.width - side) / 2;
  const maxY = (img.height - side) / 2;
  const sx = maxX + p.crop.x * maxX;
  const sy = maxY + p.crop.y * maxY;
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(img, sx, sy, side, side, 0, 0, size, size);
  const blob = await new Promise<Blob | null>((res) => c.toBlob(res, "image/jpeg", 0.95));
  if (!blob) throw new Error("The portrait couldn't be prepared.");
  return blob.arrayBuffer();
}

export function loadImage(url: string) {
  return new Promise<HTMLImageElement>((res, rej) => {
    const img = new Image();
    img.onload = () => res(img);
    img.onerror = rej;
    img.src = url;
  });
}

/** Uses the browser Shape Detection API when present; otherwise the engine checks at session start. */
export async function detectFace(url: string): Promise<FaceCheck> {
  const FD = (
    globalThis as unknown as {
      FaceDetector?: new (o?: object) => { detect: (i: CanvasImageSource) => Promise<unknown[]> };
    }
  ).FaceDetector;
  if (!FD) return "unsupported";
  try {
    const img = await loadImage(url);
    const faces = await new FD({ maxDetectedFaces: 3, fastMode: true }).detect(img);
    if (faces.length === 0) return "not-found";
    if (faces.length > 1) return "multiple";
    return "found";
  } catch {
    return "unsupported";
  }
}

/** CSS for showing a crop inside a square frame. */
export function cropStyle(p: Portrait): CSSProperties {
  const aspect = p.width / p.height;
  const wPct = aspect >= 1 ? aspect * 100 : 100;
  const hPct = aspect >= 1 ? 100 : (1 / aspect) * 100;
  const overX = wPct - 100;
  const overY = hPct - 100;
  return {
    position: "absolute",
    width: `${wPct * p.crop.zoom}%`,
    height: `${hPct * p.crop.zoom}%`,
    left: `${-((overX + (p.crop.zoom - 1) * wPct) / 2) * (1 + p.crop.x)}%`,
    top: `${-((overY + (p.crop.zoom - 1) * hPct) / 2) * (1 + p.crop.y)}%`,
    maxWidth: "none",
  };
}
