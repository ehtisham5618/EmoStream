/**
 * EmoStream engine adapter.
 *
 * Backend contracts named by the project: /ws/session, /api/export, /api/info.
 * The wire protocol below is the adapter's ASSUMPTION until checked against the engine source:
 *   client → server  JSON {type:"start", emotion, intensity, portrait: <base64 JPEG 512×512>, sample_rate: 16000}
 *                    JSON {type:"emotion", emotion, intensity}
 *                    JSON {type:"ping", t}
 *                    JSON {type:"stop"}
 *                    binary  Int16 little-endian PCM, mono, 16 kHz
 *   server → client  binary  one encoded video frame (JPEG/WebP)
 *                    JSON {type:"ready"} | {type:"stats", fps?, server_latency_ms?, peak_vram_gib?}
 *                    JSON {type:"pong", t} | {type:"error", message} | {type:"done"}
 * Keep every protocol detail in this file so the UI never depends on it directly.
 */
import type { EmotionId } from "../emotions";

export function normaliseBase(url: string) {
  return url.trim().replace(/\/+$/, "");
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
    const res = await fetch(`${b}/api/info`, signal ? { signal } : {});
    const latencyMs = Math.round(performance.now() - t0);
    if (!res.ok) return { ok: false, error: `Engine answered ${res.status}`, latencyMs };
    const raw = (await res.json()) as Record<string, unknown>;
    return { ok: true, raw, latencyMs };
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    return { ok: false, error: "Engine unreachable" };
  }
}

export async function exportSession(base: string, sessionId?: string): Promise<Blob> {
  const res = await fetch(`${normaliseBase(base)}/api/export`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
  if (!res.ok) throw new Error(`Export failed (${res.status})`);
  return res.blob();
}

export interface LiveStats {
  fps?: number;
  serverLatencyMs?: number;
  clientRttMs?: number;
  peakVramGiB?: number;
  framesReceived: number;
  framesDisplayed: number;
  framesDropped: number;
}

export type ConnState = "idle" | "connecting" | "open" | "lost" | "closed" | "error";

export interface SessionCallbacks {
  onState: (s: ConnState, detail?: string) => void;
  onReady: () => void;
  onFrame: (bitmap: ImageBitmap | HTMLImageElement) => void;
  onStats: (s: Partial<LiveStats>) => void;
  onDone: () => void;
}

export class EngineSession {
  private ws: WebSocket | null = null;
  private pingTimer = 0;
  private closedByUser = false;
  sessionId?: string;

  constructor(private base: string, private cb: SessionCallbacks) {}

  connect(start: { emotion: EmotionId; intensity: number; portrait: string }) {
    const url = wsUrl(this.base);
    if (!url) {
      this.cb.onState("error", "No engine address set");
      return;
    }
    this.cb.onState("connecting");
    let ws: WebSocket;
    try {
      ws = new WebSocket(url);
    } catch {
      this.cb.onState("error", "Engine address is not valid");
      return;
    }
    ws.binaryType = "blob";
    this.ws = ws;
    ws.onopen = () => {
      this.cb.onState("open");
      this.send({ type: "start", emotion: start.emotion, intensity: start.intensity / 100, portrait: start.portrait, sample_rate: 16000 });
      this.pingTimer = window.setInterval(() => this.send({ type: "ping", t: performance.now() }), 2000);
    };
    ws.onmessage = async (ev) => {
      if (typeof ev.data !== "string") {
        try {
          const bmp = await createImageBitmap(ev.data as Blob);
          this.cb.onFrame(bmp);
        } catch {
          this.cb.onStats({});
        }
        return;
      }
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === "ready") {
          this.sessionId = msg.session_id;
          this.cb.onReady();
        } else if (msg.type === "stats") {
          const p: Partial<LiveStats> = {};
          const fps = num(msg.fps);
          const lat = num(msg.server_latency_ms);
          const vram = num(msg.peak_vram_gib);
          if (fps !== undefined) p.fps = fps;
          if (lat !== undefined) p.serverLatencyMs = lat;
          if (vram !== undefined) p.peakVramGiB = vram;
          this.cb.onStats(p);
        } else if (msg.type === "pong" && typeof msg.t === "number") {
          this.cb.onStats({ clientRttMs: Math.round(performance.now() - msg.t) });
        } else if (msg.type === "error") {
          this.cb.onState("error", String(msg.message ?? "Engine error"));
        } else if (msg.type === "done") {
          this.cb.onDone();
        }
      } catch {
        /* ignore malformed */
      }
    };
    ws.onerror = () => this.cb.onState("error", "Could not reach the engine");
    ws.onclose = () => {
      window.clearInterval(this.pingTimer);
      this.cb.onState(this.closedByUser ? "closed" : "lost");
    };
  }

  setEmotion(emotion: EmotionId, intensity: number) {
    this.send({ type: "emotion", emotion, intensity: intensity / 100 });
  }

  sendAudio(pcm: Int16Array) {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(pcm.buffer as ArrayBuffer);
  }

  stop() {
    this.closedByUser = true;
    this.send({ type: "stop" });
    window.clearInterval(this.pingTimer);
    window.setTimeout(() => this.ws?.close(), 300);
  }

  private send(obj: unknown) {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(obj));
  }
}

const num = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : undefined);
