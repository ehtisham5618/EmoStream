import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { SyncedVoice } from "@engine/audio";
import { FramePlayer, h264Supported, type PlayerStats } from "@engine/player";
import { Chunker, FPS, SAMPLE_RATE, SAMPLES_PER_FRAME, type ServerStats } from "@engine/protocol";
import { LiveSession, type ReadyInfo, type StartupStage } from "@engine/session";
import { useMicrophone } from "@/lib/audio/useMicrophone";
import {
  engineBase,
  engineErrorMessage,
  wsUrl,
  type ConnState,
  type LiveStats,
} from "@/lib/engine/client";
import type { EmotionId } from "@/lib/emotions";
import { useSettings } from "@/lib/settings";
import { canStartSession, renderCropJpeg, studioStore, useStudio } from "@/lib/studio-store";

export type StageState =
  | "empty"
  | "preparing"
  | "ready"
  | "initializing"
  | "waiting"
  | "active"
  | "preview"
  | "paused"
  | "lost"
  | "complete"
  | "error";

export type SessionPhase =
  "idle" | "running" | "paused" | "finishing" | "lost" | "complete" | "error";

export interface EmotionEvent {
  t: number;
  emotion: EmotionId;
  intensity: number;
}

/** Measured details for the diagnostics drawer. null = not measured (yet). */
export interface SessionDiagnostics {
  codec: string | null;
  bitrateKbps: number | null;
  playoutDelayMs: number | null;
  jitterP95Ms: number | null;
  /** Picture minus sound per drawn frame, median over the last frames (ms). */
  voiceOffsetP50Ms: number | null;
  /** Share of recent drawn frames whose sound was within 80 ms. */
  voiceWithin80: number | null;
  serverP95Ms: number | null;
  serverSkipped: number;
  networkSkipped: number;
  clientDropped: number;
  uplinkLagP95Ms: number | null;
  timelineShifts: number;
  decodeErrors: number;
  /** Click → engine ready, and click → first frame on screen (ms). */
  startupReadyMs: number | null;
  startupFirstFrameMs: number | null;
  gpu: string | null;
}

const EMPTY_STATS: LiveStats = { framesReceived: 0, framesDisplayed: 0, framesDropped: 0 };
const EMPTY_DIAG: SessionDiagnostics = {
  codec: null,
  bitrateKbps: null,
  playoutDelayMs: null,
  jitterP95Ms: null,
  voiceOffsetP50Ms: null,
  voiceWithin80: null,
  serverP95Ms: null,
  serverSkipped: 0,
  networkSkipped: 0,
  clientDropped: 0,
  uplinkLagP95Ms: null,
  timelineShifts: 0,
  decodeErrors: 0,
  startupReadyMs: null,
  startupFirstFrameMs: null,
  gpu: null,
};

/** Microphone audio goes out every 80 ms, so the engine is never kept waiting for a large block. */
const MIC_CHUNK = Math.round(SAMPLE_RATE * 0.08);

/**
 * Picture minus sound for each drawn frame: when frame k was drawn vs when sample 640·k of the
 * avatar's voice was played (same computation as evaluation/benchmarks/browser_playback.py).
 */
export function pictureMinusSound(shown: [number, number][], played: [number, number][]): number[] {
  if (!shown.length || !played.length) return [];
  const sorted = [...played].sort((a, b) => a[0] - b[0]);
  const out: number[] = [];
  for (const [k, tDraw] of shown) {
    const s = k * SAMPLES_PER_FRAME;
    let lo = 0;
    let hi = sorted.length - 1;
    let i = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (sorted[mid]![0] <= s) {
        i = mid;
        lo = mid + 1;
      } else hi = mid - 1;
    }
    if (i < 0) continue;
    const [first, at] = sorted[i]!;
    if (s - first > SAMPLE_RATE * 0.3) continue; // that audio was not played (missed chunk)
    out.push(tDraw - (at + ((s - first) / SAMPLE_RATE) * 1000));
  }
  return out;
}

const median = (xs: number[]) => {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.floor(s.length / 2)] ?? null;
};

export function useStudioSession({ preparing }: { preparing: boolean }) {
  const configuredUrl = useSettings((s) => s.engineUrl);
  const engineUrl = engineBase(configuredUrl);
  const micDeviceId = useSettings((s) => s.micDeviceId);
  const portrait = useStudio((s) => s.portrait);
  const consent = useStudio((s) => s.consent);
  const voiceConsent = useStudio((s) => s.voiceConsent);
  const emotion = useStudio((s) => s.emotion);
  const intensity = useStudio((s) => s.intensity);

  const [phase, setPhase] = useState<SessionPhase>("idle");
  const [conn, setConn] = useState<ConnState>("idle");
  const [startup, setStartup] = useState<{ stage: StartupStage | null; waitedS: number }>({
    stage: null,
    waitedS: 0,
  });
  const [engineMode, setEngineMode] = useState(false);
  const [hasFrames, setHasFrames] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string>();
  const [stats, setStats] = useState<LiveStats>(EMPTY_STATS);
  const [diag, setDiag] = useState<SessionDiagnostics>(EMPTY_DIAG);
  const [events, setEvents] = useState<EmotionEvent[]>([]);
  const [frameLog, setFrameLog] = useState<number[]>([]);
  const [exporting, setExporting] = useState(false);
  const [recordingUrl, setRecordingUrl] = useState<string | null>(null);
  const [hearVoice, setHearVoiceState] = useState(false);

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const sessionRef = useRef<LiveSession | null>(null);
  const playerRef = useRef<FramePlayer | null>(null);
  const voiceRef = useRef<SyncedVoice | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunkerRef = useRef(new Chunker(MIC_CHUNK));
  const readyRef = useRef(false);
  const endingRef = useRef(false);
  const errorRef = useRef<string | null>(null);
  const finalizedRef = useRef(false);
  const serverRef = useRef<ServerStats | null>(null);
  const readyInfoRef = useRef<ReadyInfo | null>(null);
  const gpuRef = useRef<string | null>(null);
  const timesRef = useRef<{
    click: number;
    stageAt: number;
    ready: number | null;
    firstFrame: number | null;
  }>({ click: 0, stageAt: 0, ready: null, firstFrame: null });
  const diagRows = useRef<Record<string, unknown>[]>([]);
  const errorsRef = useRef<{ t: number; code: string; message: string }[]>([]);
  const startedAt = useRef(0);
  const eventsRef = useRef<EmotionEvent[]>([]);
  const timers = useRef<number[]>([]);
  const hearRef = useRef(false);
  /** Per-take measured series for Sessions and Analytics (this tab only). */
  const seriesRef = useRef({
    fps: [] as number[],
    delivered: [] as number[],
    dropped: [] as number[],
    latency: [] as number[],
    lastDropped: 0,
  });

  const mic = useMicrophone({
    deviceId: micDeviceId || undefined,
    // The microphone is opened only after the engine is ready, so nothing is captured, queued
    // or sent before then (no burst of buffered audio at the start).
    onSamples: (block) => {
      const session = sessionRef.current;
      if (!session || !readyRef.current || endingRef.current) return;
      for (const c of chunkerRef.current.push(block)) {
        const first = session.sendAudio(c);
        if (first >= 0) voiceRef.current?.push(first, c);
      }
    },
  });
  const micRef = useRef(mic);
  micRef.current = mic;

  /** Releases microphone, player, voice and recorder. The canvas keeps its last picture. */
  const release = useCallback(() => {
    timers.current.forEach((t) => window.clearTimeout(t));
    timers.current = [];
    micRef.current.stop();
    const rec = recorderRef.current;
    recorderRef.current = null;
    if (rec && rec.state !== "inactive") rec.stop();
    playerRef.current?.stop();
    const voice = voiceRef.current;
    voiceRef.current = null;
    void voice?.close();
    readyRef.current = false;
  }, []);

  const sample = useCallback(() => {
    const player = playerRef.current;
    const session = sessionRef.current;
    const p: PlayerStats | null = player?.stats() ?? null;
    const srv = serverRef.current;
    const voice = voiceRef.current;
    const diffs =
      player && voice
        ? pictureMinusSound(player.shownLog.slice(-125), voice.playedLog.slice(-400))
        : [];
    const serverSkipped = srv?.frames_dropped ?? 0;
    const networkSkipped = srv?.video?.frames_skipped_for_network ?? 0;
    const clientDropped = p ? p.droppedLate + p.droppedOverflow : 0;
    const next: LiveStats = {
      framesReceived: p?.received ?? 0,
      framesDisplayed: p?.presented ?? 0,
      framesDropped: serverSkipped + networkSkipped + clientDropped,
      ...(p && p.presented > 0 ? { fps: p.presentedFps } : {}),
      ...(srv?.latency.p50_ms !== undefined ? { serverLatencyMs: srv.latency.p50_ms } : {}),
      ...(session?.pingMs != null ? { clientRttMs: session.pingMs } : {}),
    };
    const t = timesRef.current;
    const d: SessionDiagnostics = {
      codec: p && p.codec !== "–" ? p.codec : (readyInfoRef.current?.video?.codec ?? null),
      bitrateKbps: session ? Math.round(session.receivedKbps()) : null,
      playoutDelayMs: p && p.presented > 0 ? Math.round(p.playoutDelayMs) : null,
      jitterP95Ms: p?.jitterP95Ms ?? null,
      voiceOffsetP50Ms: median(diffs),
      voiceWithin80: diffs.length
        ? diffs.filter((x) => Math.abs(x) <= 80).length / diffs.length
        : null,
      serverP95Ms: srv?.latency.p95_ms ?? null,
      serverSkipped,
      networkSkipped,
      clientDropped,
      uplinkLagP95Ms: srv?.uplink?.lag_p95_ms ?? null,
      timelineShifts: p?.timelineShifts ?? 0,
      decodeErrors: p?.decodeErrors ?? 0,
      startupReadyMs: t.ready !== null ? Math.round(t.ready - t.click) : null,
      startupFirstFrameMs: t.firstFrame !== null ? Math.round(t.firstFrame - t.click) : null,
      gpu: gpuRef.current,
    };
    return { next, d, p, srv, voice };
  }, []);

  /** Ends the take: summary in Sessions, recording available for export. */
  const finalize = useCallback(
    (outcome: "complete" | "lost" | "error") => {
      if (finalizedRef.current) return;
      finalizedRef.current = true;
      const { next, d } = sample();
      setStats(next);
      setDiag(d);
      release();
      sessionRef.current = null;
      setPhase(outcome);
      setConn(outcome === "complete" ? "closed" : outcome);
      if (timesRef.current.ready === null) return; // never started rendering: no take to list
      const st = studioStore.get();
      studioStore.set((s) => ({
        sessions: [
          {
            id: `s-${startedAt.current}`,
            avatarName: st.avatarName,
            startedAt: startedAt.current,
            durationMs: micRef.current.elapsed,
            emotionChanges: Math.max(0, eventsRef.current.length - 1),
            finalEmotion: st.emotion,
            finalIntensity: st.intensity,
            engine: true,
            framesReceived: next.framesReceived,
            outcome,
            exported: false,
            fpsPerSecond: seriesRef.current.fps,
            deliveredPerSecond: seriesRef.current.delivered,
            droppedPerSecond: seriesRef.current.dropped,
            latencyMs: seriesRef.current.latency,
            intensities: eventsRef.current.map((e) => e.intensity),
          },
          ...s.sessions,
        ],
      }));
    },
    [release, sample],
  );

  // Numbers for the UI four times a second, one diagnostics row every half second,
  // and a per-second count of frames received for the timeline.
  useEffect(() => {
    if (phase !== "running" && phase !== "paused" && phase !== "finishing") return;
    let last = 0;
    let tick = 0;
    const id = window.setInterval(() => {
      const { next, d, p, srv, voice } = sample();
      setStats(next);
      setDiag(d);
      tick++;
      if (tick % 2 === 0 && p) {
        diagRows.current.push({
          t: Math.round(performance.now()),
          client: p,
          roundTripMs: sessionRef.current?.pingMs ?? null,
          network: { kbps: d.bitrateKbps },
          voice: voice
            ? {
                scheduled: voice.scheduled,
                missed: voice.missed,
                pictureMinusSoundP50Ms: d.voiceOffsetP50Ms,
              }
            : null,
          server: srv,
          micPaused: micRef.current.state === "paused",
        });
      }
      if (tick % 4 === 0) {
        const n = p?.received ?? 0;
        setFrameLog((l) => [...l, n - last]);
        const sr = seriesRef.current;
        sr.delivered.push(n - last);
        sr.dropped.push(Math.max(0, next.framesDropped - sr.lastDropped));
        sr.lastDropped = next.framesDropped;
        if (p && p.presented > 0) sr.fps.push(Math.round(p.presentedFps * 10) / 10);
        last = n;
      }
    }, 250);
    return () => window.clearInterval(id);
  }, [phase, sample]);

  // Seconds spent in the current startup stage, so a cold start is visibly progressing.
  useEffect(() => {
    if (conn !== "connecting") return;
    const id = window.setInterval(
      () =>
        setStartup((s) => ({
          ...s,
          waitedS: Math.round((performance.now() - timesRef.current.stageAt) / 1000),
        })),
      500,
    );
    return () => window.clearInterval(id);
  }, [conn]);

  const startRecording = useCallback((voice: SyncedVoice) => {
    const canvas = canvasRef.current;
    if (!canvas || typeof MediaRecorder === "undefined" || !canvas.captureStream) return;
    const stream = canvas.captureStream(FPS);
    voice.recordStream.getAudioTracks().forEach((t) => stream.addTrack(t));
    const chunks: Blob[] = [];
    const rec = new MediaRecorder(stream);
    rec.ondataavailable = (e) => {
      if (e.data.size) chunks.push(e.data);
    };
    rec.onstop = () =>
      setRecordingUrl(
        URL.createObjectURL(new Blob(chunks, { type: rec.mimeType || "video/webm" })),
      );
    rec.start(500);
    recorderRef.current = rec;
  }, []);

  const start = useCallback(async () => {
    const st = studioStore.get();
    const check = canStartSession(st);
    if (!check.ok) {
      toast.error(check.reason);
      return;
    }
    if (sessionRef.current) return;
    const canvas = canvasRef.current;
    if (!canvas) return;

    // The avatar's voice: the sent audio, played and recorded on the picture's timeline. Created
    // here, inside the click, so the browser allows its audio output.
    const voice = new SyncedVoice(() => playerRef.current?.timelineBase ?? null);
    voice.setMonitor(hearRef.current);
    voiceRef.current = voice;

    const now = performance.now();
    timesRef.current = { click: now, stageAt: now, ready: null, firstFrame: null };
    diagRows.current = [];
    errorsRef.current = [];
    serverRef.current = null;
    readyInfoRef.current = null;
    readyRef.current = false;
    endingRef.current = false;
    errorRef.current = null;
    finalizedRef.current = false;
    chunkerRef.current = new Chunker(MIC_CHUNK);
    seriesRef.current = { fps: [], delivered: [], dropped: [], latency: [], lastDropped: 0 };
    startedAt.current = Date.now();
    eventsRef.current = [{ t: 0, emotion: st.emotion, intensity: st.intensity }];
    setEvents(eventsRef.current);
    setFrameLog([]);
    setStats(EMPTY_STATS);
    setDiag(EMPTY_DIAG);
    setHasFrames(false);
    setErrorMsg(undefined);
    if (recordingUrl) URL.revokeObjectURL(recordingUrl);
    setRecordingUrl(null);
    canvas.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);
    setEngineMode(true);
    setPhase("running");
    setConn("connecting");
    setStartup({ stage: null, waitedS: 0 });

    const fail = (message: string) => {
      errorRef.current = message;
      setErrorMsg(message);
      void voice.close();
      voiceRef.current = null;
      setPhase("error");
      setConn("error");
    };

    // Microphone permission is settled before an engine session (and its GPU time) is opened.
    if (mic.permission !== "granted") {
      const ok = await mic.probe();
      if (!ok) {
        fail(
          "Microphone access is needed to drive the avatar. Allow it in your browser's site settings, then try again.",
        );
        return;
      }
    }

    let portraitBytes: ArrayBuffer;
    try {
      portraitBytes = await renderCropJpeg(st.portrait!);
    } catch (e) {
      fail((e as Error).message || "The portrait couldn't be prepared.");
      return;
    }

    // Frames are presented on a 40 ms timeline from a small adaptive buffer, not on arrival.
    const player = new FramePlayer(canvas, {
      targetDelayMs: 80,
      maxDelayMs: 1200,
      synced: false,
      onNeedKeyFrame: () => sessionRef.current?.requestKeyFrame(),
    });
    playerRef.current = player;
    player.start();
    // Read-only handles for the measurement scripts in evaluation/benchmarks.
    (window as unknown as Record<string, unknown>)["__emostream"] = {
      player,
      voice: () => voiceRef.current,
    };

    const session = new LiveSession({
      onStage: (stage) => {
        timesRef.current.stageAt = performance.now();
        setStartup({ stage, waitedS: 0 });
      },
      onReady: (info) => {
        readyInfoRef.current = info;
        readyRef.current = true;
        timesRef.current.ready = performance.now();
        setConn("open");
        if (info.portrait?.mouth_open)
          toast("This portrait shows an open mouth", {
            description:
              "The engine closes it before animating. A photo with a closed mouth and a relaxed face gives the most natural result.",
          });
        // Microphone opens now: audio flows only once the engine and portrait are ready.
        void micRef.current.start().then((ok) => {
          if (!ok) {
            errorsRef.current.push({
              t: Math.round(performance.now()),
              code: "microphone",
              message: "microphone did not start",
            });
            errorRef.current =
              "The microphone couldn't start, so the session was stopped. Check the input device and try again.";
            setErrorMsg(errorRef.current);
            sessionRef.current?.stop();
            return;
          }
          if (voiceRef.current) startRecording(voiceRef.current);
        });
      },
      onFrame: (frame) => {
        const lat = seriesRef.current.latency;
        if (lat.length < 30000) lat.push(frame.latencyMs);
        if (timesRef.current.firstFrame === null) {
          timesRef.current.firstFrame = performance.now();
          setHasFrames(true);
        }
        void playerRef.current?.push(frame);
      },
      onStats: (s) => {
        serverRef.current = s;
      },
      onDone: (final) => {
        serverRef.current = { ...(serverRef.current ?? {}), ...final };
        // Let the buffered frames play out, then close.
        const tail = (playerRef.current?.stats().playoutDelayMs ?? 0) + 600;
        timers.current.push(window.setTimeout(() => sessionRef.current?.stop(), tail));
      },
      onError: (message, code) => {
        errorsRef.current.push({ t: Math.round(performance.now()), code: code ?? "", message });
        if (endingRef.current && code === "connection") return;
        const text = engineErrorMessage(message, code);
        errorRef.current = text;
        setErrorMsg(text);
      },
      onClose: () => {
        if (errorRef.current) finalize("error");
        else if (endingRef.current) finalize("complete");
        else finalize(readyRef.current ? "lost" : "error");
        if (!errorRef.current && !endingRef.current && !readyRef.current)
          setErrorMsg("The engine closed the connection before it was ready.");
      },
    });
    sessionRef.current = session;

    // "?video=jpeg" forces the picture-per-frame fallback, for comparisons.
    const forced = new URLSearchParams(window.location.search).get("video");
    const video = forced !== "jpeg" && (await h264Supported()) ? "h264" : "jpeg";
    session.open(
      portraitBytes,
      {
        sampleRate: SAMPLE_RATE,
        emotion: st.emotion,
        intensity: st.intensity / 100,
        model: "emostream",
        size: 512,
        video,
        bitrateKbps: 900,
      },
      wsUrl(engineUrl),
    );
  }, [engineUrl, mic, finalize, startRecording, recordingUrl]);

  const flushRest = useCallback(() => {
    const session = sessionRef.current;
    const rest = chunkerRef.current.flush();
    if (session && rest && readyRef.current) {
      const first = session.sendAudio(rest);
      if (first >= 0) voiceRef.current?.push(first, rest);
    }
  }, []);

  const pause = useCallback(() => {
    if (phase !== "running") return;
    mic.pause();
    flushRest(); // the last partial chunk before the pause is still rendered
    setPhase("paused");
  }, [mic, phase, flushRest]);

  const resume = useCallback(() => {
    if (phase !== "paused") return;
    mic.resume();
    setPhase("running");
  }, [mic, phase]);

  const stop = useCallback(() => {
    const session = sessionRef.current;
    if (!session) return;
    endingRef.current = true;
    if (!readyRef.current) {
      // Cancelled during startup: nothing was rendered.
      session.stop();
      return;
    }
    // Send what is left, then let the engine finish the last frames ("done").
    mic.stop();
    flushRest();
    setPhase("finishing");
    session.end();
    // If "done" never comes, close anyway.
    timers.current.push(window.setTimeout(() => sessionRef.current?.stop(), 10000));
  }, [mic, flushRest]);

  const reset = useCallback(() => {
    endingRef.current = true;
    finalizedRef.current = true;
    sessionRef.current?.stop();
    sessionRef.current = null;
    release();
    mic.reset();
    setPhase("idle");
    setConn("idle");
    setEngineMode(false);
    eventsRef.current = [];
    setEvents([]);
    setFrameLog([]);
    setHasFrames(false);
    setErrorMsg(undefined);
    setStats(EMPTY_STATS);
    setDiag(EMPTY_DIAG);
    const c = canvasRef.current;
    c?.getContext("2d")?.clearRect(0, 0, c.width, c.height);
  }, [mic, release]);

  // Emotion changes during a live session: log on the timeline and forward to the engine
  // (intensity 0–100 % in the UI, 0–1 on the wire).
  const lastSent = useRef<{ e: EmotionId; i: number } | null>(null);
  useEffect(() => {
    if (phase !== "running" && phase !== "paused") {
      lastSent.current = null;
      return;
    }
    const prev = lastSent.current;
    if (prev && prev.e === emotion && prev.i === intensity) return;
    const first = prev === null;
    lastSent.current = { e: emotion, i: intensity };
    if (first) return; // the start message already carried these values
    const handle = window.setTimeout(() => {
      sessionRef.current?.setEmotion(emotion, intensity / 100);
      const t = micRef.current.elapsed;
      const ev = eventsRef.current;
      const last = ev[ev.length - 1];
      let next = ev;
      if (last && last.emotion === emotion && Math.abs(last.intensity - intensity) < 1) next = ev;
      else if (last && t - last.t < 400)
        next = [...ev.slice(0, -1), { t: last.t, emotion, intensity }];
      else next = [...ev, { t, emotion, intensity }];
      eventsRef.current = next;
      setEvents(next);
    }, 120);
    return () => window.clearTimeout(handle);
  }, [emotion, intensity, phase]);

  // Leaving the Studio ends the session.
  useEffect(
    () => () => {
      endingRef.current = true;
      finalizedRef.current = true;
      sessionRef.current?.stop();
      release();
    },
    [release],
  );

  // Engine GPU for the diagnostics file.
  useEffect(() => {
    let cancelled = false;
    fetch(`${engineUrl}/api/info`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((info) => {
        if (!cancelled && info && typeof info.gpu === "string") gpuRef.current = info.gpu;
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [engineUrl]);

  const setHearVoice = useCallback((on: boolean) => {
    hearRef.current = on;
    setHearVoiceState(on);
    const v = voiceRef.current;
    if (v) {
      v.setMonitor(on);
      void v.ctx.resume();
    }
  }, []);

  /** The take as recorded in this browser: the engine's frames with the avatar's voice. */
  const doExport = useCallback(async () => {
    if (!recordingUrl) {
      toast.error("No recording of this take is available.");
      return;
    }
    setExporting(true);
    try {
      const a = document.createElement("a");
      a.href = recordingUrl;
      a.download = `emostream-session-${startedAt.current}.webm`;
      a.click();
      const id = `s-${startedAt.current}`;
      studioStore.set((s) => ({
        sessions: s.sessions.map((x) => (x.id === id ? { ...x, exported: true } : x)),
      }));
      toast.success("Export downloaded");
    } finally {
      setExporting(false);
    }
  }, [recordingUrl]);

  const saveDiagnostics = useCallback(() => {
    const st = studioStore.get();
    const t = timesRef.current;
    const body = {
      client: "web-studio",
      build: typeof __BUILD__ === "string" ? __BUILD__ : null,
      savedAt: new Date().toISOString(),
      userAgent: navigator.userAgent,
      engine: engineUrl,
      gpu: gpuRef.current,
      model: "emostream",
      emotion: st.emotion,
      intensity: st.intensity / 100,
      phase,
      startup: {
        readyMs: t.ready !== null ? Math.round(t.ready - t.click) : null,
        firstFrameMs: t.firstFrame !== null ? Math.round(t.firstFrame - t.click) : null,
      },
      ready: readyInfoRef.current,
      emotionTimeline: eventsRef.current,
      errors: errorsRef.current,
      summary: { stats, diagnostics: diag },
      finalServer: serverRef.current,
      rows: diagRows.current,
    };
    const blob = new Blob([JSON.stringify(body, null, 1)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "emostream-diagnostics.json";
    a.click();
    window.setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }, [engineUrl, phase, stats, diag]);

  const live = phase === "running" || phase === "paused" || phase === "finishing";
  let stage: StageState;
  if (!portrait) stage = preparing ? "preparing" : "empty";
  else if (preparing) stage = "preparing";
  else if (phase === "error") stage = "error";
  else if (phase === "lost") stage = "lost";
  else if (phase === "complete") stage = "complete";
  else if (phase === "paused") stage = "paused";
  else if (phase === "running" || phase === "finishing") {
    if (conn === "connecting") stage = "initializing";
    else if (hasFrames) stage = "active";
    else stage = "waiting";
  } else stage = "ready";

  const startupDetail =
    conn !== "connecting"
      ? undefined
      : startup.stage === "initializing_portrait"
        ? `Building your avatar from the portrait on the engine… ${startup.waitedS} s`
        : mic.state === "requesting"
          ? "Waiting for microphone permission…"
          : `Connecting to the engine… ${startup.waitedS} s${startup.waitedS >= 8 ? ". After an idle period the GPU worker needs up to a minute to start." : ""}`;

  const baseCheck = canStartSession({ portrait, consent, voiceConsent });
  const canStart = live
    ? {
        ok: false as const,
        reason: phase === "finishing" ? "Finishing the last frames…" : "A session is running.",
      }
    : baseCheck;

  return {
    stage,
    phase,
    conn,
    engineMode,
    engineUrl,
    errorMsg,
    stats,
    diag,
    events,
    frameLog,
    mic,
    canvasRef,
    canStart,
    exporting,
    recordingUrl,
    startupDetail,
    hearVoice,
    setHearVoice,
    start,
    pause,
    resume,
    stop,
    reset,
    doExport,
    saveDiagnostics,
  };
}

export type StudioSession = ReturnType<typeof useStudioSession>;
