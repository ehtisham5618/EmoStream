import { describe, expect, it } from "vitest";
import { startMessage } from "@engine/protocol";
import { pictureMinusSound } from "@/components/studio/useStudioSession";
import { engineBase, engineErrorMessage, wsUrl } from "@/lib/engine/client";

describe("engine address", () => {
  it("defaults to the page's own origin", () => {
    expect(engineBase("")).toBe(window.location.origin);
    expect(wsUrl(engineBase(""))).toBe(
      window.location.origin.replace(/^http/, "ws") + "/ws/session",
    );
  });
  it("a configured address wins and is normalised", () => {
    expect(engineBase(" https://engine.example.org/ ")).toBe("https://engine.example.org");
  });
});

describe("start message", () => {
  it("carries both consents, H.264, and intensity on the 0–1 scale", () => {
    const m = JSON.parse(
      startMessage({
        sampleRate: 16000,
        emotion: "happy",
        intensity: 60 / 100,
        model: "emostream",
        size: 512,
        video: "h264",
        bitrateKbps: 900,
      }),
    );
    expect(m).toMatchObject({
      type: "start",
      consent: { portrait: true, audio: true },
      sample_rate: 16000,
      emotion: "happy",
      intensity: 0.6,
      video: "h264",
    });
    expect(typeof m.client_build).toBe("string");
  });
});

describe("error messages", () => {
  it("explains the engine's error codes in plain language", () => {
    expect(engineErrorMessage("x", "busy")).toMatch(/Another session/);
    expect(engineErrorMessage("x", "no_face")).toMatch(/No face/);
    expect(engineErrorMessage("x", "client_outdated")).toMatch(/Reload/);
    expect(engineErrorMessage("Something odd", "unknown_code")).toBe("Something odd");
  });
});

describe("voice and lips offset", () => {
  it("is zero when each frame is drawn exactly when its sound plays", () => {
    // chunk of 1,280 samples (2 frames) starting at sample 0, played at t = 1000 ms
    const played: [number, number][] = [
      [0, 1000],
      [1280, 1080],
    ];
    const shown: [number, number][] = [
      [0, 1000],
      [1, 1040],
      [2, 1080],
      [3, 1120],
    ];
    expect(pictureMinusSound(shown, played)).toEqual([0, 0, 0, 0]);
  });
  it("measures a picture that is late", () => {
    expect(pictureMinusSound([[1, 1100]], [[0, 1000]])).toEqual([60]);
  });
  it("skips frames whose audio was never played", () => {
    expect(pictureMinusSound([[100, 5000]], [[0, 1000]])).toEqual([]);
  });
});
