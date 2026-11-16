import { describe, expect, it } from "vitest";
import { PlayoutClock } from "./player";

const live = { targetDelayMs: 120, maxDelayMs: 600, synced: false };

describe("PlayoutClock", () => {
  it("spaces frames 40 ms apart regardless of bursty arrival", () => {
    const c = new PlayoutClock(live);
    // five frames arrive together every 200 ms, as the server sends them
    const due: number[] = [];
    for (let block = 0; block < 4; block++)
      for (let k = 0; k < 5; k++) {
        const idx = block * 5 + k;
        expect(c.onArrival(idx, 1000 + block * 200 + k)).toBe(true);
        due.push(c.base! + idx * 40);
      }
    for (let i = 1; i < due.length; i++) expect(due[i] - due[i - 1]).toBeCloseTo(40, 6);
    expect(c.dueIndex(c.base! + 79)).toBe(1);
    expect(c.dueIndex(c.base! - 1)).toBe(-1);
  });

  it("buffers more after repeated lateness, and never beyond the cap", () => {
    const c = new PlayoutClock(live);
    expect(c.onArrival(0, 0)).toBe(true); // base = 120
    expect(c.onArrival(1, 260)).toBe(false); // due at 160: 100 ms late, first offence -> dropped
    expect(c.onArrival(2, 300)).toBe(true); // due at 200: late again -> timeline moves later
    expect(c.shifts).toBe(1);
    expect(c.base!).toBeCloseTo(120 + 100 + 40, 6);
    const capped = new PlayoutClock({ ...live, maxDelayMs: 150 });
    capped.onArrival(0, 0);
    expect(capped.onArrival(1, 400)).toBe(false);
    expect(capped.onArrival(2, 440)).toBe(false); // would need more than the cap: dropped instead
    expect(capped.shifts).toBe(0);
    // ...but if the source stays behind, the timeline is re-anchored instead of freezing
    let shown = 0;
    for (let k = 3; k < 12; k++) if (capped.onArrival(k, 400 + k * 40)) shown++;
    expect(capped.resyncs).toBeGreaterThan(0);
    expect(shown).toBeGreaterThan(3);
  });

  it("moves the timeline earlier when frames keep arriving with spare time", () => {
    const c = new PlayoutClock(live);
    c.onArrival(0, 0); // base 120
    const before = c.base!;
    // every frame arrives 300 ms before it is due: delay can be reduced
    for (let k = 1; k <= 120; k++) c.onArrival(k, c.base! + k * 40 - 300);
    expect(c.base!).toBeLessThan(before);
    expect(c.extraMs).toBeLessThan(0);
  });

  it("jumps forward instead of building seconds of delay when a backlog arrives", () => {
    const c = new PlayoutClock(live);
    c.onArrival(0, 0); // base 120
    // the source delivers 3 s of frames within 300 ms (working off a backlog)
    for (let k = 1; k <= 75; k++) c.onArrival(k, k * 4);
    expect(c.jumps).toBeGreaterThan(0);
    const delayOfNewest = c.base! + 75 * 40 - 300;
    expect(delayOfNewest).toBeLessThanOrEqual(600);
  });

  it("never moves the timeline when locked to audio", () => {
    const c = new PlayoutClock({ targetDelayMs: 300, maxDelayMs: 600, synced: true });
    c.onArrival(0, 0);
    const base = c.base!;
    for (let k = 1; k < 80; k++) c.onArrival(k, base + k * 40 + (k % 7 === 0 ? 50 : -200));
    expect(c.base!).toBe(base);
    expect(c.shifts).toBe(0);
    expect(c.onArrival(100, base + 100 * 40 + 1)).toBe(false); // late -> dropped
  });
});
