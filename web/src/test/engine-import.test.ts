import { describe, expect, it } from "vitest";
import { audioMessage, parseFrame, portraitMessage, TAG_AUDIO, TAG_PORTRAIT } from "@engine/protocol";

describe("shared engine protocol", () => {
  it("tags the portrait and audio messages as the backend expects", () => {
    expect(portraitMessage(new Uint8Array([1, 2]).buffer)[0]).toBe(TAG_PORTRAIT);
    expect(audioMessage(new Float32Array(4))[0]).toBe(TAG_AUDIO);
    expect(parseFrame(new Uint8Array([0x77]).buffer)).toBeNull();
  });
});
