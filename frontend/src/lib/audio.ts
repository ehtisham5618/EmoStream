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
): Promise<MicCapture> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
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
    for (let i = 0; i < block.length; i++) sum += block[i] * block[i];
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
    out[i] = input[a] + (input[b] - input[a]) * (x - a);
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
