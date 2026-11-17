// Microphone capture and audio-file decoding, both delivering 16 kHz mono float samples.

import { SAMPLE_RATE } from "./protocol";

export interface MicCapture {
  stream: MediaStream;
  sampleRate: number;
  stop: () => Promise<void>;
}

/**
 * Opens the microphone and calls `onSamples` with mono float blocks. The audio context is
 * asked for 16 kHz; browsers that refuse it report their own rate and the caller resamples.
 */
export async function startMicrophone(
  onSamples: (samples: Float32Array) => void,
  onLevel: (rms: number) => void,
  options: { deviceId?: string } = {},
): Promise<MicCapture> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true,
      ...(options.deviceId ? { deviceId: { exact: options.deviceId } } : {}),
    },
  });
  let ctx: AudioContext;
  try {
    ctx = new AudioContext({ sampleRate: SAMPLE_RATE, latencyHint: "interactive" });
  } catch {
    ctx = new AudioContext({ latencyHint: "interactive" });
  }
  await ctx.audioWorklet.addModule(`${import.meta.env.BASE_URL}pcm-worklet.js`);
  const source = ctx.createMediaStreamSource(stream);
  const node = new AudioWorkletNode(ctx, "pcm-capture", { numberOfInputs: 1, numberOfOutputs: 0 });
  node.port.onmessage = (ev: MessageEvent<Float32Array>) => {
    const block = ev.data;
    let sum = 0;
    for (let i = 0; i < block.length; i++) sum += block[i]! * block[i]!;
    onLevel(Math.sqrt(sum / block.length));
    onSamples(ctx.sampleRate === SAMPLE_RATE ? block : resampleLinear(block, ctx.sampleRate, SAMPLE_RATE));
  };
  source.connect(node);
  return {
    stream,
    sampleRate: ctx.sampleRate,
    stop: async () => {
      node.port.onmessage = null;
      source.disconnect();
      stream.getTracks().forEach((t) => t.stop());
      await ctx.close();
    },
  };
}

/** Linear-interpolation resampling of one block. Used only when 16 kHz capture is unavailable. */
export function resampleLinear(input: Float32Array, from: number, to: number): Float32Array {
  if (from === to) return input;
  const n = Math.floor((input.length * to) / from);
  const out = new Float32Array(n);
  const ratio = from / to;
  for (let i = 0; i < n; i++) {
    const x = i * ratio;
    const a = Math.floor(x);
    const b = Math.min(a + 1, input.length - 1);
    out[i] = input[a]! + (input[b]! - input[a]!) * (x - a);
  }
  return out;
}

/** Decodes any audio file the browser understands to 16 kHz mono. */
export async function decodeAudioFile(file: File): Promise<{ samples: Float32Array; buffer: AudioBuffer }> {
  const bytes = await file.arrayBuffer();
  const probe = new AudioContext();
  let decoded: AudioBuffer;
  try {
    decoded = await probe.decodeAudioData(bytes.slice(0));
  } finally {
    await probe.close();
  }
  const length = Math.ceil(decoded.duration * SAMPLE_RATE);
  const offline = new OfflineAudioContext(1, length, SAMPLE_RATE);
  const src = offline.createBufferSource();
  src.buffer = decoded;
  src.connect(offline.destination);
  src.start();
  const rendered = await offline.startRendering();
  return { samples: rendered.getChannelData(0).slice(0), buffer: rendered };
}

/**
 * Plays the voice that drives the avatar on the avatar's own timeline.
 *
 * The picture for a moment of speech appears some hundreds of milliseconds after it was
 * spoken (network, model, buffering). Heard live, the voice is therefore always ahead of
 * the face. Here every chunk of sent audio is scheduled at the time its video frames are
 * presented (sample n plays at  timeline base + n / 16000 s), so sound and picture stay
 * together whatever the delay is, which is what a viewer of the avatar gets.
 *
 * The result always goes to `recordStream` (for the session recording); it reaches the
 * speakers only when monitoring is switched on.
 */
export class SyncedVoice {
  readonly ctx: AudioContext;
  readonly recordStream: MediaStream;
  private readonly dest: MediaStreamAudioDestinationNode;
  private readonly monitor: GainNode;
  private queue: { first: number; samples: Float32Array }[] = [];
  private timer: number;
  scheduled = 0;
  /** Chunks whose slot had already passed when the timeline became known. */
  missed = 0;
  /** [first sample, time it reaches the output] of recent chunks, for measuring offset. */
  readonly playedLog: [number, number][] = [];

  constructor(private readonly timelineBase: () => number | null) {
    this.ctx = new AudioContext({ latencyHint: "interactive" });
    this.dest = this.ctx.createMediaStreamDestination();
    this.recordStream = this.dest.stream;
    this.monitor = this.ctx.createGain();
    this.monitor.gain.value = 0;
    this.monitor.connect(this.ctx.destination);
    // The recording stream must never go idle: while no chunk is playing (a pause in the
    // schedule after the timeline moved) Chrome delivers no audio at all to a recorder,
    // and everything after the pause ends up early in the file (measured: 0.5-0.7 s).
    // An inaudible tone (-100 dB) keeps it running.
    const keepAlive = this.ctx.createOscillator();
    const quiet = this.ctx.createGain();
    quiet.gain.value = 0.00001;
    keepAlive.connect(quiet).connect(this.dest);
    keepAlive.start();
    this.timer = window.setInterval(() => this.pump(), 40);
  }

  setMonitor(on: boolean): void {
    this.monitor.gain.value = on ? 1 : 0;
  }

  /** `first` is the index of the chunk's first sample within the session. */
  push(first: number, samples: Float32Array): void {
    this.queue.push({ first, samples: samples.slice() });
    if (this.queue.length > 400) this.queue.shift();
  }

  private pump(): void {
    const base = this.timelineBase();
    if (base === null) return;
    const now = performance.now();
    while (this.queue.length) {
      const c = this.queue[0]!;
      const at = base + (c.first / SAMPLE_RATE) * 1000;
      if (at - now > 200) break; // scheduled close to its time, so timeline moves are followed
      this.queue.shift();
      const duration = (c.samples.length / SAMPLE_RATE) * 1000;
      if (at + duration <= now) {
        this.missed++;
        continue;
      }
      const buf = this.ctx.createBuffer(1, c.samples.length, SAMPLE_RATE);
      buf.copyToChannel(c.samples as Float32Array<ArrayBuffer>, 0);
      const src = this.ctx.createBufferSource();
      src.buffer = buf;
      src.connect(this.dest);
      src.connect(this.monitor);
      // Map the performance clock onto the audio clock with the pair the browser reports
      // for "the sample being output now"; currentTime alone runs ahead by the output latency.
      const stamp = this.ctx.getOutputTimestamp();
      const when = stamp.contextTime !== undefined && stamp.performanceTime
        ? stamp.contextTime + (at - stamp.performanceTime) / 1000
        : this.ctx.currentTime + (at - now) / 1000;
      const late = this.ctx.currentTime - when;
      if (late <= 0) src.start(when);
      else if (late * 1000 < duration) src.start(this.ctx.currentTime, late);
      else {
        this.missed++;
        continue;
      }
      this.scheduled++;
      this.playedLog.push([c.first, at]);
      if (this.playedLog.length > 2000) this.playedLog.shift();
    }
  }

  async close(): Promise<void> {
    window.clearInterval(this.timer);
    this.queue = [];
    await this.ctx.close().catch(() => undefined);
  }
}
