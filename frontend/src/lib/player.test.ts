import { describe, expect, it } from "vitest";
import { PlayoutClock } from "./player";

const live = { targetDelayMs: 120, maxDelayMs: 600, synced: false };

describe("PlayoutClock", () => {
  it("spaces frames 40 ms apart regardless of bursty arrival", () => {
    const c = new PlayoutClock(live);
    // five frames arrive together every 200 ms
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

  it("shows a late frame by moving the timeline, and never beyond the cap", () => {
    const c = new PlayoutClock(live);
    expect(c.onArrival(0, 0)).toBe(true); // base = 120
    expect(c.onArrival(1, 260)).toBe(true); // due at 160, 100 ms late: timeline moves, frame is shown
    expect(c.shifts).toBe(1);
    expect(c.base! + 40).toBeGreaterThan(260); // its new slot is still ahead
    expect(c.base!).toBeLessThanOrEqual(600 + 120);
    const capped = new PlayoutClock({ ...live, maxDelayMs: 150 });
    capped.onArrival(0, 0);
    expect(capped.onArrival(1, 900)).toBe(false); // a straggler beyond the cap: dropped
    expect(capped.shifts).toBe(0);
    // ...but if the whole stream stays that late, the timeline is re-anchored instead of freezing
    let shown = 0;
    for (let k = 2; k < 12; k++) if (capped.onArrival(k, 900 + k * 40)) shown++;
    expect(capped.resyncs).toBeGreaterThan(0);
    expect(shown).toBeGreaterThan(3);
  });

  it("absorbs a jittery link without dropping frames once it has seen the jitter", () => {
    const c = new PlayoutClock({ targetDelayMs: 80, maxDelayMs: 1200, synced: false });
    let dropped = 0;
    let late = 0;
    // arrival lateness cycles 0..280 ms (bursts of eight frames), for 20 s
    for (let k = 0; k < 500; k++) {
      const now = 1000 + Math.floor(k / 8) * 320 + 300;
      const ok = c.onArrival(k, now);
      if (!ok) dropped++;
      else if (k > 50 && c.base! + k * 40 < now) late++;
    }
    expect(dropped).toBe(0);
    expect(late).toBe(0);
    expect(c.jitterP95()!).toBeGreaterThan(200);
    // delay stays near the jitter, not at the cap
    expect(c.playoutDelay(499, 1000 + Math.floor(499 / 8) * 320 + 300)).toBeLessThan(500);
  });

  it("gives delay back when the link calms down", () => {
    const c = new PlayoutClock(live);
    c.onArrival(0, 0);
    c.onArrival(1, 500); // one bad moment pushes the timeline later
    const pushed = c.base!;
    for (let k = 2; k <= 400; k++) c.onArrival(k, k * 40); // then 16 s of steady arrival
    expect(c.base!).toBeLessThan(pushed);
    expect(c.base!).toBeLessThanOrEqual(120 + 40 + 1);
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
