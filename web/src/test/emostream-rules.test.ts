import { describe, expect, it } from "vitest";
import { VALIDATION, HARDWARE } from "@/lib/benchmarks";
import { ILLUSTRATIVE_CONFUSION, macroF1 } from "@/lib/demo-data";
import { faceFor } from "@/lib/emotions";
import { wsUrl } from "@/lib/engine/client";
import { canStartSession, validatePortraitFile, validatePortraitSize, type Portrait } from "@/lib/studio-store";

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
  it("needs a portrait", () => {
    expect(canStartSession({ portrait: null, consent: true }).ok).toBe(false);
  });
  it("needs consent even with a portrait", () => {
    expect(canStartSession({ portrait: portrait(), consent: false }).ok).toBe(false);
  });
  it("starts with portrait and consent", () => {
    expect(canStartSession({ portrait: portrait(), consent: true }).ok).toBe(true);
  });
  it("refuses when no face or several faces were detected", () => {
    expect(canStartSession({ portrait: portrait({ faceCheck: "not-found" }), consent: true }).ok).toBe(false);
    expect(canStartSession({ portrait: portrait({ faceCheck: "multiple" }), consent: true }).ok).toBe(false);
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
    expect(VALIDATION).toMatchObject({ fps: 25, peakVramGiB: 2.77, serverP50Ms: 269, serverP95Ms: 319, arcface: 0.93, emotionMacroF1: 0.651 });
  });
  it("only the L40S carries performance figures; RTX 4050 is unverified", () => {
    expect(HARDWARE.filter((h) => h.fps).map((h) => h.gpu)).toEqual(["NVIDIA L40S"]);
    expect(HARDWARE.find((h) => h.gpu.includes("4050"))?.status).toBe("unverified");
  });
  it("illustrative confusion matrix stays consistent with reported macro-F1", () => {
    expect(Math.abs(macroF1(ILLUSTRATIVE_CONFUSION) - 0.651)).toBeLessThan(0.01);
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
