// Paced presentation of avatar frames.
//
// Frames reach the browser unevenly: the server produces them in small groups and the
// network adds jitter. Drawing each frame the moment it arrives shows bursts and gaps.
// This player decodes frames as they arrive, holds them in a small bounded buffer, and
// presents frame k at  base + k * 40 ms  from a requestAnimationFrame loop, so motion is
// evenly paced. All statistics are taken at the moment a frame is actually drawn.
//
// Late-frame policy (explicit, never silent):
//   * A frame that arrives after a newer frame was already shown is dropped ("late").
//   * If the frame due now has not arrived, the previous image stays ("hold").
//   * Live mode: repeated lateness moves the timeline later (more buffering), up to a cap;
//     sustained slack moves it earlier again. Each move is counted.
//   * Synced mode (audio is being played back): the timeline never moves, because it is
//     locked to the audio clock; late frames are dropped instead.

import { FPS } from "./protocol";

const FRAME_MS = 1000 / FPS;

export interface PlayerOptions {
  /** Delay between a frame's arrival and its presentation that the player aims for. */
  targetDelayMs: number;
  /** Upper bound of that delay; beyond it frames are dropped rather than delayed further. */
  maxDelayMs: number;
  /** true when audio playback is locked to this timeline (uploaded audio). */
  synced: boolean;
  /** Called once, with the performance.now() time at which frame 0 is (or would be) shown. */
  onTimeline?: (frameZeroTime: number) => void;
}

export interface PlayerStats {
  presented: number;          // distinct frames drawn
  presentedFps: number;       // distinct frames drawn per second, last 2 s
  intervalP50Ms: number | null; // time between consecutive drawn frames
  intervalP95Ms: number | null;
  intervalMaxMs: number | null;
  ageP50Ms: number | null;    // arrival -> drawn
  ageP95Ms: number | null;
  received: number;
  receivedFps: number;
  droppedLate: number;        // arrived too late to be shown
  droppedOverflow: number;    // discarded because the buffer was full
  skipped: number;            // never shown because a newer frame was due (catch-up)
  holds: number;              // refreshes where the due frame was missing
  outOfOrder: number;
  duplicates: number;
  bufferDepth: number;
  playoutDelayMs: number;     // current arrival -> presentation offset
  timelineShifts: number;     // times the timeline was moved (live mode only)
  decodeP50Ms: number | null;
  avOffsetMs: number | null;  // synced mode: drawn frame time minus audio clock
}

interface Pending {
  index: number;
  bitmap: ImageBitmap;
  arrival: number;
}

function quantile(xs: number[], q: number): number | null {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.floor(q * s.length))];
}

export const MAX_BUFFERED_FRAMES = 30;

/** Pure scheduling core, separated from the DOM so it can be unit-tested. */
export class PlayoutClock {
  base: number | null = null; // performance time of frame 0
  shifts = 0;
  private lateStreak = 0;
  private slack: number[] = [];
  /** Buffering added on top of the target delay, in ms (can be negative after catching up). */
  extraMs = 0;
  /** Times the timeline had to be re-anchored because the source stayed behind. */
  resyncs = 0;
  /** Times the timeline jumped forward because frames arrived far ahead of it. */
  jumps = 0;

  constructor(private readonly opt: Pick<PlayerOptions, "targetDelayMs" | "maxDelayMs" | "synced">) {}

  /** Call for every arriving frame. Returns true if the frame can still be shown. */
  onArrival(index: number, now: number): boolean {
    if (this.base === null) this.base = now + this.opt.targetDelayMs - index * FRAME_MS;
    const due = this.base + index * FRAME_MS;
    const slack = due - now; // > 0: arrived in time
    this.slack.push(slack);
    if (this.slack.length > 50) this.slack.shift();
    if (!this.opt.synced && slack > this.opt.maxDelayMs) {
      // Frames are arriving far ahead of the timeline (the source is working off a
      // backlog). Showing them on the old timeline would mean seconds of delay, so jump:
      // re-anchor on this frame; older buffered frames are skipped when it is presented.
      this.base = now + this.opt.targetDelayMs - index * FRAME_MS;
      this.extraMs = 0;
      this.shifts++;
      this.jumps++;
      this.lateStreak = 0;
      this.slack = [];
      return true;
    }
    if (slack >= 0) {
      this.lateStreak = 0;
      if (!this.opt.synced && this.slack.length === 50) {
        // Sustained spare time: move the timeline earlier by one frame to cut delay.
        const min = Math.min(...this.slack);
        if (min > this.opt.targetDelayMs + FRAME_MS) {
          this.base -= FRAME_MS;
          this.extraMs -= FRAME_MS;
          this.shifts++;
          this.slack = [];
        }
      }
      return true;
    }
    if (this.opt.synced) return false; // locked to audio: late frames are dropped
    this.lateStreak++;
    if (this.lateStreak >= 2) {
      // Repeatedly late: buffer more, but never beyond the cap.
      const add = -slack + FRAME_MS;
      if (this.opt.targetDelayMs + this.extraMs + add <= this.opt.maxDelayMs) {
        this.base += add;
        this.extraMs += add;
        this.shifts++;
        this.lateStreak = 0;
        this.slack = [];
        return true;
      }
      if (this.lateStreak >= 6) {
        // The source is persistently behind (more than the cap allows). Dropping every
        // frame would freeze the picture, so re-anchor the timeline on this frame and
        // carry on from there; the event is counted in `shifts`.
        this.extraMs += -slack + this.opt.targetDelayMs;
        this.base = now + this.opt.targetDelayMs - index * FRAME_MS;
        this.shifts++;
        this.resyncs++;
        this.lateStreak = 0;
        this.slack = [];
        return true;
      }
    }
    return false;
  }

  /** Index of the frame that should be on screen at `now`, or -1 before the start. */
  dueIndex(now: number): number {
    if (this.base === null) return -1;
    return Math.floor((now - this.base) / FRAME_MS);
  }

  playoutDelay(index: number, arrival: number): number {
    return this.base === null ? 0 : this.base + index * FRAME_MS - arrival;
  }
}

export class FramePlayer {
  private clock: PlayoutClock;
  private buffer = new Map<number, Pending>();
  private raf = 0;
  private lastShown = -1;
  private highestSeen = -1;
  private running = false;
  private announced = false;
  private presentTimes: number[] = [];
  private arrivalTimes: number[] = [];
  private ages: number[] = [];
  private decodeMs: number[] = [];
  private seen = new Set<number>();
  private counters = { presented: 0, received: 0, droppedLate: 0, droppedOverflow: 0, skipped: 0, holds: 0, outOfOrder: 0, duplicates: 0 };
  private lastDelay = 0;
  private lastAvOffset: number | null = null;
  /** Synced mode: returns the audio clock in ms since the audio started, or null. */
  audioClockMs: (() => number | null) | null = null;

  constructor(private readonly canvas: HTMLCanvasElement, private readonly opt: PlayerOptions) {
    this.clock = new PlayoutClock(opt);
  }

  start(): void {
    if (this.running) return;
    this.running = true;
    const tick = (now: number) => {
      if (!this.running) return;
      this.present(now);
      this.raf = requestAnimationFrame(tick);
    };
    this.raf = requestAnimationFrame(tick);
  }

  stop(): void {
    this.running = false;
    cancelAnimationFrame(this.raf);
    this.buffer.forEach((p) => p.bitmap.close());
    this.buffer.clear();
  }

  /** Feed one frame as received from the server. Decoding runs off the main thread. */
  async push(index: number, jpeg: Uint8Array): Promise<void> {
    const arrival = performance.now();
    this.counters.received++;
    this.arrivalTimes.push(arrival);
    if (this.seen.has(index)) {
      this.counters.duplicates++;
      return;
    }
    this.seen.add(index);
    if (index < this.highestSeen) this.counters.outOfOrder++;
    this.highestSeen = Math.max(this.highestSeen, index);
    const usable = this.clock.onArrival(index, arrival);
    if (!this.announced && this.clock.base !== null) {
      this.announced = true;
      this.opt.onTimeline?.(this.clock.base);
    }
    if (!usable || index <= this.lastShown) {
      this.counters.droppedLate++;
      return;
    }
    const bitmap = await createImageBitmap(new Blob([jpeg as BlobPart], { type: "image/jpeg" }));
    this.decodeMs.push(performance.now() - arrival);
    if (this.decodeMs.length > 100) this.decodeMs.shift();
    if (!this.running || index <= this.lastShown) {
      bitmap.close();
      if (this.running) this.counters.droppedLate++;
      return;
    }
    this.buffer.set(index, { index, bitmap, arrival });
    if (this.buffer.size > MAX_BUFFERED_FRAMES) {
      const oldest = Math.min(...this.buffer.keys());
      this.buffer.get(oldest)!.bitmap.close();
      this.buffer.delete(oldest);
      this.counters.droppedOverflow++;
    }
    this.lastDelay = this.clock.playoutDelay(index, arrival);
  }

  private present(now: number): void {
    const due = this.clock.dueIndex(now);
    if (due < 0 || due <= this.lastShown) return;
    // Newest buffered frame that is due.
    let pick = -1;
    for (const k of this.buffer.keys()) if (k <= due && k > pick) pick = k;
    if (pick < 0) {
      if (this.lastShown >= 0) this.counters.holds++;
      return;
    }
    for (const k of [...this.buffer.keys()]) {
      if (k < pick) {
        this.buffer.get(k)!.bitmap.close();
        this.buffer.delete(k);
        this.counters.skipped++;
      }
    }
    const frame = this.buffer.get(pick)!;
    this.buffer.delete(pick);
    if (this.canvas.width !== frame.bitmap.width) {
      this.canvas.width = frame.bitmap.width;
      this.canvas.height = frame.bitmap.height;
    }
    this.canvas.getContext("2d")!.drawImage(frame.bitmap, 0, 0);
    frame.bitmap.close();
    this.lastShown = pick;
    this.counters.presented++;
    this.presentTimes.push(now);
    this.ages.push(now - frame.arrival);
    if (this.ages.length > 250) this.ages.shift();
    const audio = this.audioClockMs?.();
    this.lastAvOffset = audio === null || audio === undefined ? null : pick * FRAME_MS - audio;
  }

  stats(): PlayerStats {
    const now = performance.now();
    const win = 2000;
    this.presentTimes = this.presentTimes.filter((t) => now - t < 10000);
    this.arrivalTimes = this.arrivalTimes.filter((t) => now - t < win);
    const recent = this.presentTimes.filter((t) => now - t < win);
    const intervals: number[] = [];
    for (let i = 1; i < this.presentTimes.length; i++) intervals.push(this.presentTimes[i] - this.presentTimes[i - 1]);
    return {
      ...this.counters,
      presentedFps: recent.length / (win / 1000),
      receivedFps: this.arrivalTimes.length / (win / 1000),
      intervalP50Ms: quantile(intervals, 0.5),
      intervalP95Ms: quantile(intervals, 0.95),
      intervalMaxMs: intervals.length ? Math.max(...intervals) : null,
      ageP50Ms: quantile(this.ages, 0.5),
      ageP95Ms: quantile(this.ages, 0.95),
      bufferDepth: this.buffer.size,
      playoutDelayMs: this.lastDelay,
      timelineShifts: this.clock.shifts,
      decodeP50Ms: quantile(this.decodeMs, 0.5),
      avOffsetMs: this.lastAvOffset,
    };
  }
}
