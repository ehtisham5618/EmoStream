import { describe, expect, it } from "vitest";
import { audioMessage, Chunker, frameOfSample, parseFrame, portraitMessage, startMessage, TAG_AUDIO, TAG_FRAME, TAG_PORTRAIT } from "./protocol";

describe("protocol", () => {
  it("encodes audio as tagged little-endian PCM16 and clips", () => {
    const m = audioMessage(new Float32Array([0, 1, -1, 2, -2, 0.5]));
    expect(m[0]).toBe(TAG_AUDIO);
    const v = new DataView(m.buffer);
    expect([1, 3, 5, 7, 9, 11].map((o) => v.getInt16(o, true))).toEqual([0, 32767, -32768, 32767, -32768, 16384]);
  });

  it("tags the portrait and always declares consent in the start message", () => {
    expect(portraitMessage(new Uint8Array([9, 8]).buffer)).toEqual(new Uint8Array([TAG_PORTRAIT, 9, 8]));
    const s = JSON.parse(startMessage({ sampleRate: 16000, emotion: "sad", intensity: 0.4, model: "emostream", size: 512, video: "h264" }));
    expect(s).toMatchObject({ type: "start", consent: { portrait: true, audio: true }, emotion: "sad", intensity: 0.4, sample_rate: 16000 });
  });

  it("parses a frame header and rejects other messages", () => {
    const buf = new Uint8Array(9 + 3);
    const v = new DataView(buf.buffer);
    v.setUint8(0, TAG_FRAME);
    v.setUint32(1, 70000, true);
    v.setUint32(5, 123, true);
    buf.set([1, 2, 3], 9);
    const f = parseFrame(buf.buffer)!;
    expect([f.index, f.latencyMs, Array.from(f.data)]).toEqual([70000, 123, [1, 2, 3]]);
    expect(parseFrame(new Uint8Array([TAG_AUDIO, 0, 0, 0, 0, 0, 0, 0, 0]).buffer)).toBeNull();
    expect(parseFrame(new Uint8Array(4).buffer)).toBeNull();
  });

  it("chunks a stream into fixed blocks without losing or reordering samples", () => {
    const c = new Chunker(4);
    const out: number[] = [];
    for (const block of [[1, 2, 3], [4, 5], [6, 7, 8, 9, 10, 11]]) {
      for (const chunk of c.push(new Float32Array(block))) {
        expect(chunk.length).toBe(4);
        out.push(...chunk);
      }
    }
    expect(out).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
    expect(Array.from(c.flush()!)).toEqual([9, 10, 11]);
    expect(c.flush()).toBeNull();
  });

  it("maps samples to 40 ms frames", () => {
    expect([0, 639, 640, 16000].map(frameOfSample)).toEqual([0, 0, 1, 25]);
  });
});
