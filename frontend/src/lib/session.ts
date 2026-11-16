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
  AvatarFrame,
  VideoCodec,
} from "./protocol";

export interface ReadyInfo {
  portrait?: { mouth_open?: boolean; lip_open_ratio?: number; mouth_closed_automatically?: boolean };
  algorithmic_delay_ms?: [number, number] | null;
  video?: { codec: VideoCodec; bitrate_kbps: number | null };
  frontend_build?: string | null;
}

/** Startup stages, in order. The page shows each one; nothing is "live" before "ready". */
export type StartupStage = "connecting" | "initializing_portrait";

export interface SessionEvents {
  onStage: (stage: StartupStage) => void;
  onReady: (info: ReadyInfo) => void;
  onFrame: (frame: AvatarFrame, roundTripMs: number | null) => void;
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
  private framesReceived = 0;
  private bytesIn: [number, number][] = [];
  private timer: number | null = null;
  /** Network round trip of a small message, ms (median of the last few). */
  pingMs: number | null = null;
  private pings: number[] = [];

  constructor(private readonly events: SessionEvents) {}

  open(portrait: ArrayBuffer, options: StartOptions): void {
    const ws = new WebSocket(sessionUrl());
    ws.binaryType = "arraybuffer";
    this.ws = ws;
    this.events.onStage("connecting");
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
      this.framesReceived++;
      this.bytesIn.push([performance.now(), (ev.data as ArrayBuffer).byteLength]);
      const sent = this.sentAt[frame.index];
      this.events.onFrame(frame, sent === undefined ? null : performance.now() - sent);
    };
    ws.onerror = () => this.events.onError(this.ready
      ? "The connection to the server was lost."
      : "Could not reach the server. If it has been idle, it may still be starting; try again in a moment.", "connection");
    ws.onclose = () => {
      if (this.timer !== null) window.clearInterval(this.timer);
      this.timer = null;
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
      // Tell the server five times a second how many frames have arrived (it paces the
      // video on that), and measure the round trip of a small message once a second.
      let n = 0;
      this.timer = window.setInterval(() => {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
        this.ws.send(JSON.stringify({ type: "ack", frames: this.framesReceived }));
        if (n++ % 5 === 0) this.ws.send(JSON.stringify({ type: "ping", t: performance.now() }));
      }, 200);
      this.events.onReady((msg.session ?? {}) as ReadyInfo);
    } else if (msg.type === "status") {
      if (msg.stage === "initializing_portrait") this.events.onStage("initializing_portrait");
    } else if (msg.type === "pong") {
      if (typeof msg.t === "number") {
        this.pings.push(performance.now() - msg.t);
        if (this.pings.length > 5) this.pings.shift();
        this.pingMs = [...this.pings].sort((a, b) => a - b)[Math.floor(this.pings.length / 2)];
      }
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
   * Returns the index of the first sample within the session, or -1 if it was not sent.
   */
  sendAudio(samples: Float32Array): number {
    if (!this.ws) return -1;
    if (!this.ready) {
      this.discardedSamples += samples.length;
      return -1;
    }
    const first = this.samplesSent;
    const before = Math.floor(this.samplesSent / SAMPLES_PER_FRAME);
    this.samplesSent += samples.length;
    const after = Math.floor(this.samplesSent / SAMPLES_PER_FRAME);
    const now = performance.now();
    for (let k = before; k < after; k++) this.sentAt[k] = now;
    this.ws.send(audioMessage(samples));
    return first;
  }

  /** The H.264 decoder lost its place: ask for a key frame. */
  requestKeyFrame(): void {
    if (this.ws && this.ready) this.ws.send(JSON.stringify({ type: "keyframe" }));
  }

  /** Video bitrate actually received over the last two seconds, kbit/s. */
  receivedKbps(): number {
    const now = performance.now();
    this.bytesIn = this.bytesIn.filter(([t]) => now - t < 2000);
    return (this.bytesIn.reduce((a, [, n]) => a + n, 0) * 8) / 2000;
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
