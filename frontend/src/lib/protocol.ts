// Wire protocol of a live session. Mirrors backend/streaming/protocol.py.

export const TAG_AUDIO = 0x01;
export const TAG_FRAME = 0x02;
export const TAG_VIDEO = 0x03;
export const TAG_PORTRAIT = 0x10;
export const FRAME_HEADER_BYTES = 9; // tag u8 | frame index u32 LE | latency ms u32 LE
export const VIDEO_HEADER_BYTES = 10; // ... | flags u8 (bit 0: key frame)
export type VideoCodec = "jpeg" | "h264";

export const FPS = 25;
export const SAMPLE_RATE = 16000;
export const SAMPLES_PER_FRAME = SAMPLE_RATE / FPS; // 640
export const CHUNK_SAMPLES = SAMPLE_RATE / 5; // 200 ms

export const EMOTIONS = ["neutral", "happy", "sad", "angry", "surprised"] as const;
export type Emotion = (typeof EMOTIONS)[number];
export type ModelName = "emostream" | "ditto";

export interface StartOptions {
  sampleRate: number;
  emotion: Emotion;
  intensity: number;
  model: ModelName;
  size: 256 | 384 | 512;
  video: VideoCodec;
  bitrateKbps?: number;
}

export function startMessage(o: StartOptions): string {
  return JSON.stringify({
    type: "start",
    consent: { portrait: true, audio: true },
    sample_rate: o.sampleRate,
    emotion: o.emotion,
    intensity: o.intensity,
    model: o.model,
    size: o.size,
    jpeg_quality: 80,
    video: o.video,
    bitrate_kbps: o.bitrateKbps ?? 900,
    client_build: typeof __BUILD__ === "string" ? __BUILD__ : "",
  });
}

function tagged(tag: number, payload: Uint8Array): Uint8Array {
  const out = new Uint8Array(payload.length + 1);
  out[0] = tag;
  out.set(payload, 1);
  return out;
}

export function portraitMessage(image: ArrayBuffer): Uint8Array {
  return tagged(TAG_PORTRAIT, new Uint8Array(image));
}

/** Float samples in [-1, 1] -> tagged little-endian 16-bit PCM. */
export function audioMessage(samples: Float32Array): Uint8Array {
  const out = new Uint8Array(1 + samples.length * 2);
  out[0] = TAG_AUDIO;
  const view = new DataView(out.buffer);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(1 + i * 2, Math.round(s < 0 ? s * 32768 : s * 32767), true);
  }
  return out;
}

/** One encoded picture from the server: a JPEG image or an H.264 access unit. */
export interface AvatarFrame {
  index: number;
  latencyMs: number;
  codec: VideoCodec;
  key: boolean;
  data: Uint8Array;
}

export function parseFrame(data: ArrayBuffer): AvatarFrame | null {
  if (data.byteLength < FRAME_HEADER_BYTES) return null;
  const view = new DataView(data);
  const tag = view.getUint8(0);
  if (tag === TAG_FRAME) {
    return { index: view.getUint32(1, true), latencyMs: view.getUint32(5, true), codec: "jpeg", key: true,
      data: new Uint8Array(data, FRAME_HEADER_BYTES) };
  }
  if (tag === TAG_VIDEO && data.byteLength >= VIDEO_HEADER_BYTES) {
    return { index: view.getUint32(1, true), latencyMs: view.getUint32(5, true), codec: "h264",
      key: (view.getUint8(9) & 1) === 1, data: new Uint8Array(data, VIDEO_HEADER_BYTES) };
  }
  return null;
}

export interface ServerStats {
  frames: number;
  frames_dropped: number;
  audio_s: number;
  compute_fps: number | null;
  latency: { n: number; p50_ms?: number; p95_ms?: number; max_ms?: number; output_fps?: number | null };
  stages_ms?: Record<string, number>;
  gpu?: { torch_alloc_gib?: number; torch_reserved_gib?: number };
  queued_chunks?: number;
  video?: { codec: VideoCodec; target_kbps: number | null; sent_kbps: number; frames_sent: number;
    frames_skipped_for_network: number; in_flight_frames: number; backlog_ms: number; congestion_events: number };
  uplink?: { lag_p95_ms: number | null; lag_max_ms: number | null };
}

/** Splits a stream of float samples into fixed-size chunks, keeping the remainder. */
export class Chunker {
  private buf = new Float32Array(0);
  constructor(private readonly size: number = CHUNK_SAMPLES) {}

  push(samples: Float32Array): Float32Array[] {
    const merged = new Float32Array(this.buf.length + samples.length);
    merged.set(this.buf);
    merged.set(samples, this.buf.length);
    const out: Float32Array[] = [];
    let pos = 0;
    while (merged.length - pos >= this.size) {
      out.push(merged.slice(pos, pos + this.size));
      pos += this.size;
    }
    this.buf = merged.slice(pos);
    return out;
  }

  flush(): Float32Array | null {
    const rest = this.buf;
    this.buf = new Float32Array(0);
    return rest.length ? rest : null;
  }
}

/** Index of the video frame that contains a given sample. */
export function frameOfSample(sample: number): number {
  return Math.floor(sample / SAMPLES_PER_FRAME);
}
