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

export interface ReadyInfo {
  portrait?: { mouth_open?: boolean; lip_open_ratio?: number; mouth_closed_automatically?: boolean };
  algorithmic_delay_ms?: [number, number] | null;
}

export interface SessionEvents {
  onReady: (info: ReadyInfo) => void;
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
  /** Samples captured before the server was ready; they are discarded, not queued. */
  discardedSamples = 0;

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
      this.events.onReady((msg.session ?? {}) as ReadyInfo);
    } else if (msg.type === "stats") {
      this.events.onStats(msg as unknown as ServerStats);
    } else if (msg.type === "done") {
      this.events.onDone(msg.stats as ServerStats);
    } else if (msg.type === "error") {
      this.events.onError(String(msg.message ?? "The server reported an error."), String(msg.code ?? ""));
    }
  }

  /**
   * Sends 16 kHz mono samples. Audio captured before the server is ready is dropped:
   * queueing it would hand the server several seconds of backlog at once, and a live
   * avatar would start seconds behind the speaker and stay there.
   */
  sendAudio(samples: Float32Array): void {
    if (!this.ws) return;
    if (!this.ready) {
      this.discardedSamples += samples.length;
      return;
    }
    const before = Math.floor(this.samplesSent / SAMPLES_PER_FRAME);
    this.samplesSent += samples.length;
    const after = Math.floor(this.samplesSent / SAMPLES_PER_FRAME);
    const now = performance.now();
    for (let k = before; k < after; k++) this.sentAt[k] = now;
    this.ws.send(audioMessage(samples));
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
