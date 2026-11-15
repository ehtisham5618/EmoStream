// One live avatar session over a WebSocket: audio out, frames and statistics in.

import {
  audioMessage,
  Emotion,
  parseFrame,
  portraitMessage,
  SAMPLE_RATE,
  SAMPLES_PER_FRAME,
  ServerStats,
  startMessage,
  StartOptions,
  VideoFrame,
} from "./protocol";

export interface SessionEvents {
  onReady: () => void;
  onFrame: (frame: VideoFrame, roundTripMs: number | null) => void;
  onStats: (stats: ServerStats) => void;
  onDone: (stats: ServerStats) => void;
  onError: (message: string, code?: string) => void;
  onClose: () => void;
}

export function sessionUrl(): string {
  const base = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";
  if (base) return base.replace(/^http/, "ws") + "/ws/session";
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${location.host}/ws/session`;
}

export class LiveSession {
  private ws: WebSocket | null = null;
  private samplesSent = 0;
  // sentAt[k] = time at which the audio completing frame k left the browser
  private sentAt: number[] = [];
  private ready = false;
  private pending: Uint8Array[] = [];

  constructor(private readonly events: SessionEvents) {}

  open(portrait: ArrayBuffer, options: StartOptions): void {
    const ws = new WebSocket(sessionUrl());
    ws.binaryType = "arraybuffer";
    this.ws = ws;
    ws.onopen = () => {
      ws.send(startMessage(options));
      ws.send(portraitMessage(portrait));
    };
    ws.onmessage = (ev) => {
      if (typeof ev.data === "string") {
        this.onText(ev.data);
        return;
      }
      const frame = parseFrame(ev.data as ArrayBuffer);
      if (!frame) return;
      const sent = this.sentAt[frame.index];
      this.events.onFrame(frame, sent === undefined ? null : performance.now() - sent);
    };
    ws.onerror = () => this.events.onError("The connection to the server failed.");
    ws.onclose = () => {
      this.ws = null;
      this.events.onClose();
    };
  }

  private onText(raw: string): void {
    let msg: { type: string; [k: string]: unknown };
    try {
      msg = JSON.parse(raw);
    } catch {
      return;
    }
    if (msg.type === "ready") {
      this.ready = true;
      for (const m of this.pending) this.ws?.send(m);
      this.pending = [];
      this.events.onReady();
    } else if (msg.type === "stats") {
      this.events.onStats(msg as unknown as ServerStats);
    } else if (msg.type === "done") {
      this.events.onDone(msg.stats as ServerStats);
    } else if (msg.type === "error") {
      this.events.onError(String(msg.message ?? "The server reported an error."), String(msg.code ?? ""));
    }
  }

  /** Sends 16 kHz mono samples. Audio captured before the server is ready is queued. */
  sendAudio(samples: Float32Array, sampleRate: number = SAMPLE_RATE): void {
    if (!this.ws) return;
    const message = audioMessage(samples);
    const before = Math.floor((this.samplesSent * SAMPLE_RATE) / sampleRate / SAMPLES_PER_FRAME);
    this.samplesSent += samples.length;
    const after = Math.floor((this.samplesSent * SAMPLE_RATE) / sampleRate / SAMPLES_PER_FRAME);
    const now = performance.now();
    for (let k = before; k < after; k++) this.sentAt[k] = now;
    if (this.ready) this.ws.send(message);
    else this.pending.push(message);
  }

  setEmotion(emotion: Emotion, intensity: number): void {
    if (this.ws && this.ready) this.ws.send(JSON.stringify({ type: "emotion", emotion, intensity }));
  }

  /** No more audio: the server renders the remaining frames and reports "done". */
  end(): void {
    if (this.ws && this.ready) this.ws.send(JSON.stringify({ type: "end" }));
  }

  /** Stops immediately and discards anything still queued on the server. */
  stop(): void {
    if (!this.ws) return;
    try {
      if (this.ready) this.ws.send(JSON.stringify({ type: "stop" }));
    } finally {
      this.ws.close();
    }
  }

  get seconds(): number {
    return this.samplesSent / SAMPLE_RATE;
  }
}
