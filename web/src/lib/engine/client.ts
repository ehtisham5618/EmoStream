/**
 * EmoStream engine adapter: addresses, engine info, and the live-statistics shape the UI shows.
 *
 * The wire protocol itself is NOT defined here. The Studio uses the reference client shared with
 * the diagnostics client (`@engine/*` = frontend/src/lib: protocol.ts, session.ts, player.ts,
 * audio.ts), which implements docs/integration/frontend_backend_contract.md:
 *   start (JSON, consent + options) → 0x10 portrait → status → ready → 0x01 PCM16 audio …
 *   ← 0x03 H.264 video frames (0x02 JPEG fallback), stats, emotion_ack, pong, done, error
 *
 * Engine address: empty (the default) means the engine that serves this page, i.e. the same
 * origin. A build can point elsewhere with VITE_ENGINE_URL, and Settings can override both.
 */

export function normaliseBase(url: string) {
  return url.trim().replace(/\/+$/, "");
}

/** Base URL of the engine: settings override, then build-time VITE_ENGINE_URL, then this origin. */
export function engineBase(settingsUrl = ""): string {
  const configured = normaliseBase(settingsUrl) || normaliseBase((import.meta.env["VITE_ENGINE_URL"] as string | undefined) ?? "");
  if (configured) return configured;
  return typeof window === "undefined" ? "" : window.location.origin;
}

export function wsUrl(base: string, path = "/ws/session") {
  const b = normaliseBase(base);
  if (!b) return "";
  return b.replace(/^http(s?):\/\//i, (_m, s) => `ws${s}://`) + path;
}

export interface EngineInfo {
  ok: boolean;
  raw?: Record<string, unknown>;
  error?: string;
  latencyMs?: number;
}

export async function fetchEngineInfo(base: string, signal?: AbortSignal): Promise<EngineInfo> {
  const b = normaliseBase(base);
  if (!b) return { ok: false, error: "No engine address set" };
  const t0 = performance.now();
  try {
    const res = await fetch(`${b}/api/info`, { cache: "no-store", ...(signal ? { signal } : {}) });
    const latencyMs = Math.round(performance.now() - t0);
    if (!res.ok) return { ok: false, error: `Engine answered ${res.status}`, latencyMs };
    const raw = (await res.json()) as Record<string, unknown>;
    return { ok: true, raw, latencyMs };
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    return { ok: false, error: "Engine unreachable" };
  }
}

/** What the Studio shows while a session runs. Every field is measured; undefined = not measured. */
export interface LiveStats {
  /** Distinct frames drawn on screen per second (last 2 s), measured in this browser. */
  fps?: number;
  /** Server-side audio-to-frame latency, median over the session (engine `stats`). */
  serverLatencyMs?: number;
  /** Round trip of a small message over the session's WebSocket (ping/pong median). */
  clientRttMs?: number;
  /** Not reported per session by the engine (TensorRT memory is not included in its GPU field). */
  peakVramGiB?: number;
  framesReceived: number;
  framesDisplayed: number;
  /** Frames never shown: skipped by the engine to bound delay, held back for the network, or late/overflowing here. */
  framesDropped: number;
}

export type ConnState = "idle" | "connecting" | "open" | "lost" | "closed" | "error";

/** Plain-language messages for the engine's error codes (contract §3.4). */
export function engineErrorMessage(message: string, code?: string): string {
  switch (code) {
    case "busy":
      return "Another session is using the avatar engine. Try again in a few seconds.";
    case "no_face":
      return "No face was found in this portrait. Choose a clear, front-facing photo.";
    case "consent_required":
      return "Both consents are needed before the engine can start.";
    case "client_outdated":
      return "This page is out of date. Reload it (Ctrl+Shift+R) and start again.";
    case "bad_portrait":
    case "portrait_too_large":
      return "The engine couldn't read this portrait. Try a JPG or PNG under 10 MB.";
    case "session_too_long":
      return "Sessions are limited to 15 minutes of audio. Start a new take.";
    case "overloaded":
      return "The engine fell too far behind. Start a new take.";
    case "model_unavailable":
      return "The EmoStream model isn't loaded on this engine.";
    case "connection":
      return message;
    case "internal_error":
      return `${message}. The session was stopped; you can start again.`;
    default:
      return message || "The engine returned an error.";
  }
}
