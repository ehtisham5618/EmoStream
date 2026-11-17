import { describe, expect, it } from "vitest";
import { CURRENT, VALIDATION, HARDWARE } from "@/lib/benchmarks";
import { faceFor } from "@/lib/emotions";
import { wsUrl } from "@/lib/engine/client";
import {
  canStartSession,
  validatePortraitFile,
  validatePortraitSize,
  type Portrait,
} from "@/lib/studio-store";

const portrait = (over: Partial<Portrait> = {}): Portrait => ({
  url: "blob:x",
  name: "p.jpg",
  type: "image/jpeg",
  sizeBytes: 1000,
  width: 800,
  height: 800,
  crop: { x: 0, y: 0, zoom: 1 },
  faceCheck: "unsupported",
  addedAt: 0,
  ...over,
});

describe("session start rules", () => {
  const both = { consent: true, voiceConsent: true };
  it("needs a portrait", () => {
    expect(canStartSession({ portrait: null, ...both }).ok).toBe(false);
  });
  it("needs portrait consent even with a portrait", () => {
    expect(canStartSession({ portrait: portrait(), consent: false, voiceConsent: true }).ok).toBe(
      false,
    );
  });
  it("needs voice consent before any audio is sent", () => {
    expect(canStartSession({ portrait: portrait(), consent: true, voiceConsent: false }).ok).toBe(
      false,
    );
  });
  it("starts with a portrait and both consents", () => {
    expect(canStartSession({ portrait: portrait(), ...both }).ok).toBe(true);
  });
  it("refuses when no face or several faces were detected", () => {
    expect(canStartSession({ portrait: portrait({ faceCheck: "not-found" }), ...both }).ok).toBe(
      false,
    );
    expect(canStartSession({ portrait: portrait({ faceCheck: "multiple" }), ...both }).ok).toBe(
      false,
    );
  });
});

describe("portrait requirements", () => {
  it("accepts JPG, PNG, WebP up to 10 MB", () => {
    expect(validatePortraitFile({ type: "image/png", size: 10 * 1024 * 1024 })).toBeNull();
    expect(validatePortraitFile({ type: "image/gif", size: 100 })).not.toBeNull();
    expect(validatePortraitFile({ type: "image/jpeg", size: 10 * 1024 * 1024 + 1 })).not.toBeNull();
  });
  it("needs at least 256 px on the short side", () => {
    expect(validatePortraitSize(255, 900)).not.toBeNull();
    expect(validatePortraitSize(256, 256)).toBeNull();
  });
});

describe("validated figures", () => {
  it("match the validation report", () => {
    expect(VALIDATION).toMatchObject({
      fps: 25,
      peakVramGiB: 2.77,
      serverP50Ms: 269,
      serverP95Ms: 319,
      arcface: 0.93,
      emotionMacroF1: 0.651,
    });
  });
  it("only the L40S carries performance figures; RTX 4050 is unverified", () => {
    expect(HARDWARE.filter((h) => h.fps).map((h) => h.gpu)).toEqual(["NVIDIA L40S"]);
    expect(HARDWARE.find((h) => h.gpu.includes("4050"))?.status).toBe("unverified");
  });
  it("historical engine figures name the model and date they come from", () => {
    expect(VALIDATION).toMatchObject({ model: "reg", date: "15 Nov 2026" });
  });
  it("live-model figures match the 17 Nov articulation report", () => {
    expect(CURRENT).toMatchObject({
      model: "ph_aug",
      lseC: 5.08,
      lseD: 9.15,
      emotionMacroF1: 0.777,
      arcface: 0.876,
    });
  });
});

describe("engine adapter", () => {
  it("derives the session socket from the engine address", () => {
    expect(wsUrl("http://localhost:8000/")).toBe("ws://localhost:8000/ws/session");
    expect(wsUrl("https://gpu.example.org")).toBe("wss://gpu.example.org/ws/session");
    expect(wsUrl("")).toBe("");
  });
});

describe("emotion intensity", () => {
  it("0% is neutral and 100% is the full expression", () => {
    expect(faceFor("happy", 0).mouthCurve).toBe(0);
    expect(faceFor("happy", 100).mouthCurve).toBe(1);
    expect(faceFor("happy", 50).mouthCurve).toBeCloseTo(0.5);
  });
});
