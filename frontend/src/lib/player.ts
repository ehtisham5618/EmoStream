// Paced presentation of avatar frames.
//
// Frames reach the browser unevenly: the network delivers them in bursts and with pauses.
// Drawing each frame the moment it arrives shows exactly that. This player decodes frames
// as they arrive (JPEG images or an H.264 stream), holds them in a small buffer, and
// presents frame k at  base + k * 40 ms  from a requestAnimationFrame loop.
//
// The buffer adapts to the link, the way a WebRTC jitter buffer does:
//   * For every frame the player notes how late it arrived relative to a steady 40 ms
//     cadence. The timeline is placed behind the 95th percentile of the last four seconds.
//   * A frame that arrives after its slot moves the timeline later at once (it is shown,
//     not dropped), up to a cap. Beyond the cap single stragglers are dropped; if the whole
//     stream has moved, the timeline is re-anchored.
//   * When the link calms down the timeline creeps earlier again, one frame per second.
//   * Synced mode (an uploaded recording is being played back): the timeline never moves,
//     because the sound is locked to it; late frames are dropped instead.
// The avatar's voice is scheduled on the same timeline, so picture and sound stay together
// whatever the delay is. All statistics are taken at the moment a frame is actually drawn.

import { AvatarFrame, FPS } from "./protocol";

const FRAME_MS = 1000 / FPS;

export interface PlayerOptions {
  /** Safety margin kept between a frame's expected arrival and its presentation. */
  targetDelayMs: number;
  /** Upper bound of the buffering; beyond it frames are dropped rather than delayed further. */
  maxDelayMs: number;
  /** true when audio playback is locked to this timeline (uploaded audio). */
  synced: boolean;
  /** Called once, with the performance.now() time at which frame 0 is (or would be) shown. */
  onTimeline?: (frameZeroTime: number) => void;
  /** The H.264 decoder failed and needs a key frame from the server. */
  onNeedKeyFrame?: () => void;
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
  jitterP95Ms: number | null; // spread of arrival lateness over the last four seconds
  timelineShifts: number;     // times the timeline was moved (live mode only)
  decodeP50Ms: number | null;
  decodeErrors: number;
  codec: string;
  avOffsetMs: number | null;  // synced mode: drawn frame time minus audio clock
}

type Picture = ImageBitmap | VideoFrame;

interface Pending {
  index: number;
  picture: Picture;
  arrival: number;
}

function quantile(xs: number[], q: number): number | null {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.floor(q * s.length))]!;
}

export const MAX_BUFFERED_FRAMES = 40;
const WINDOW = 100; // arrivals remembered for the jitter estimate (4 s)

/** Pure scheduling core, separated from the DOM so it can be unit-tested. */
export class PlayoutClock {
  base: number | null = null; // performance time of frame 0
  shifts = 0;
  /** Times the timeline had to be re-anchored because the whole stream moved later. */
  resyncs = 0;
  /** Times the timeline jumped forward because frames arrived far ahead of it. */
  jumps = 0;
  private lateStreak = 0;
  private sinceCheck = 0;
  /** arrival time minus index * 40 ms, for recent frames: how late each one was. */
  private offsets: number[] = [];

  constructor(private readonly opt: Pick<PlayerOptions, "targetDelayMs" | "maxDelayMs" | "synced">) {}

  /** Where the timeline should sit for the jitter seen recently. */
  private desired(): number {
    return quantile(this.offsets, 0.95)! + this.opt.targetDelayMs;
  }

  /** Spread of arrival lateness (95th percentile minus best), ms. */
  jitterP95(): number | null {
    if (this.offsets.length < 5) return null;
    return quantile(this.offsets, 0.95)! - Math.min(...this.offsets);
  }

  private anchor(offset: number): void {
    this.base = offset + this.opt.targetDelayMs;
    this.offsets = [offset];
    this.lateStreak = 0;
    this.sinceCheck = 0;
  }

  /** Call for every arriving frame. Returns true if the frame can still be shown. */
  onArrival(index: number, now: number): boolean {
    const offset = now - index * FRAME_MS;
    if (this.base === null) {
      this.anchor(offset);
      return true;
    }
    const slack = this.base - offset; // > 0: arrived before its slot
    if (this.opt.synced) return slack >= 0; // locked to audio: never move, drop late frames
    this.offsets.push(offset);
    if (this.offsets.length > WINDOW) this.offsets.shift();

    if (slack > this.opt.maxDelayMs) {
      // Frames are arriving far ahead of the timeline (the source is working off a
      // backlog). Showing them on the old timeline would mean seconds of delay, so jump:
      // re-anchor on this frame; older buffered frames are skipped when it is presented.
      this.anchor(offset);
      this.shifts++;
      this.jumps++;
      return true;
    }
    if (slack >= 0) {
      this.lateStreak = 0;
      if (++this.sinceCheck >= 25 && this.offsets.length >= 50) {
        // Once a second: if the link has been calmer than the buffer assumes, give one
        // frame of delay back.
        this.sinceCheck = 0;
        if (this.base - this.desired() > FRAME_MS) {
          this.base -= FRAME_MS;
          this.shifts++;
        }
      }
      return true;
    }
    // Late. Move the timeline so that this frame, and the jitter seen recently, fit.
    this.lateStreak++;
    const want = Math.max(this.desired(), offset + FRAME_MS);
    if (want - Math.min(...this.offsets) <= this.opt.maxDelayMs + this.opt.targetDelayMs) {
      this.base = want;
      this.shifts++;
      this.lateStreak = 0;
      return true;
    }
    if (this.lateStreak >= 6) {
      // Not a straggler: the whole stream is now this late (for example after a stall).
      // Dropping every frame would freeze the picture, so start again from here.
      this.anchor(offset);
      this.shifts++;
      this.resyncs++;
      return true;
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

/** True if this browser can decode the H.264 stream the server sends. */
export async function h264Supported(): Promise<boolean> {
  try {
    if (typeof VideoDecoder === "undefined") return false;
    const r = await VideoDecoder.isConfigSupported({ codec: H264_CODEC, optimizeForLatency: true });
    return !!r.supported;
  } catch {
    return false;
  }
}

const H264_CODEC = "avc1.42E01F"; // constrained baseline, as the server encodes

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
  private counters = { presented: 0, received: 0, droppedLate: 0, droppedOverflow: 0, skipped: 0, holds: 0, outOfOrder: 0, duplicates: 0, decodeErrors: 0 };
  private lastPaint = 0;
  /** [frame index, time drawn] of recent frames, for measuring picture-sound offset. */
  readonly shownLog: [number, number][] = [];
  private decoder: VideoDecoder | null = null;
  private waitingForKey = true;
  private codec = "–";
  /** H.264 frames handed to the decoder: index -> arrival time and whether it is still wanted. */
  private inDecoder = new Map<number, { arrival: number; usable: boolean }>();
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
    this.buffer.forEach((p) => p.picture.close());
    this.buffer.clear();
    if (this.decoder && this.decoder.state !== "closed") this.decoder.close();
    this.decoder = null;
  }

  /** performance.now() time at which frame 0 is shown on the current timeline. */
  get timelineBase(): number | null {
    return this.clock.base;
  }

  /** Feed one frame as received from the server. Decoding runs off the main thread. */
  async push(frame: AvatarFrame): Promise<void> {
    const { index } = frame;
    const arrival = performance.now();
    this.counters.received++;
    this.arrivalTimes.push(arrival);
    this.codec = frame.codec;
    if (this.seen.has(index)) {
      this.counters.duplicates++;
      return;
    }
    this.seen.add(index);
    if (index < this.highestSeen) this.counters.outOfOrder++;
    this.highestSeen = Math.max(this.highestSeen, index);
    const usable = this.clock.onArrival(index, arrival) && index > this.lastShown;
    if (!this.announced && this.clock.base !== null) {
      this.announced = true;
      this.opt.onTimeline?.(this.clock.base);
    }
    if (frame.codec === "h264") {
      // Every frame of the stream must pass through the decoder, wanted or not.
      this.decodeH264(frame, arrival, usable);
      return;
    }
    if (!usable) {
      this.counters.droppedLate++;
      return;
    }
    const bitmap = await createImageBitmap(new Blob([frame.data as BlobPart], { type: "image/jpeg" }));
    this.accept(index, bitmap, arrival, true);
  }

  private decodeH264(frame: AvatarFrame, arrival: number, usable: boolean): void {
    if (!this.decoder || this.decoder.state === "closed") {
      this.decoder = new VideoDecoder({
        output: (picture) => {
          const index = Math.round(picture.timestamp / (FRAME_MS * 1000));
          const meta = this.inDecoder.get(index);
          this.inDecoder.delete(index);
          this.accept(index, picture, meta?.arrival ?? performance.now(), meta?.usable ?? true);
        },
        error: () => {
          this.counters.decodeErrors++;
          this.waitingForKey = true;
          this.inDecoder.clear();
          this.opt.onNeedKeyFrame?.();
        },
      });
      this.decoder.configure({ codec: H264_CODEC, optimizeForLatency: true });
      this.waitingForKey = true;
    }
    if (this.waitingForKey && !frame.key) {
      this.counters.droppedLate++;
      return;
    }
    this.waitingForKey = false;
    this.inDecoder.set(frame.index, { arrival, usable });
    try {
      this.decoder.decode(new EncodedVideoChunk({
        type: frame.key ? "key" : "delta", timestamp: Math.round(frame.index * FRAME_MS * 1000), data: frame.data,
      }));
    } catch {
      this.counters.decodeErrors++;
      this.waitingForKey = true;
      this.opt.onNeedKeyFrame?.();
    }
  }

  private accept(index: number, picture: Picture, arrival: number, usable: boolean): void {
    this.decodeMs.push(performance.now() - arrival);
    if (this.decodeMs.length > 100) this.decodeMs.shift();
    if (!this.running || !usable || index <= this.lastShown) {
      picture.close();
      if (this.running) this.counters.droppedLate++;
      return;
    }
    this.buffer.set(index, { index, picture, arrival });
    if (this.buffer.size > MAX_BUFFERED_FRAMES) {
      const oldest = Math.min(...this.buffer.keys());
      this.buffer.get(oldest)!.picture.close();
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
      if (this.lastShown >= 0) {
        this.counters.holds++;
        // Keep the canvas "live" while the picture is held: a recording of the canvas
        // otherwise receives no video frames during a stall and loses step with its sound.
        if (now - this.lastPaint >= FRAME_MS) {
          this.lastPaint = now;
          this.canvas.getContext("2d")!.drawImage(this.canvas, 0, 0);
        }
      }
      return;
    }
    for (const k of [...this.buffer.keys()]) {
      if (k < pick) {
        this.buffer.get(k)!.picture.close();
        this.buffer.delete(k);
        this.counters.skipped++;
      }
    }
    const frame = this.buffer.get(pick)!;
    this.buffer.delete(pick);
    const pic = frame.picture;
    const w = "displayWidth" in pic ? pic.displayWidth : pic.width;
    const h = "displayHeight" in pic ? pic.displayHeight : pic.height;
    if (this.canvas.width !== w || this.canvas.height !== h) {
      this.canvas.width = w;
      this.canvas.height = h;
    }
    this.canvas.getContext("2d")!.drawImage(pic, 0, 0);
    pic.close();
    this.lastShown = pick;
    this.lastPaint = now;
    this.shownLog.push([pick, now]);
    if (this.shownLog.length > 3000) this.shownLog.shift();
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
    for (let i = 1; i < this.presentTimes.length; i++) intervals.push(this.presentTimes[i]! - this.presentTimes[i - 1]!);
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
      jitterP95Ms: this.clock.jitterP95(),
      codec: this.codec,
      timelineShifts: this.clock.shifts,
      decodeP50Ms: quantile(this.decodeMs, 0.5),
      avOffsetMs: this.lastAvOffset,
    };
  }
}
