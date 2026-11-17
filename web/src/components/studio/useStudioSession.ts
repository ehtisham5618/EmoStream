import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { useMicrophone } from "@/lib/audio/useMicrophone";
import { EngineSession, exportSession, type ConnState, type LiveStats } from "@/lib/engine/client";
import type { EmotionId } from "@/lib/emotions";
import { useSettings } from "@/lib/settings";
import { canStartSession, renderCrop, studioStore, useStudio } from "@/lib/studio-store";

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

export interface EmotionEvent {
  t: number;
  emotion: EmotionId;
  intensity: number;
}

const EMPTY_STATS: LiveStats = { framesReceived: 0, framesDisplayed: 0, framesDropped: 0 };

export function useStudioSession({ preparing }: { preparing: boolean }) {
  const engineUrl = useSettings((s) => s.engineUrl);
  const micDeviceId = useSettings((s) => s.micDeviceId);
  const portrait = useStudio((s) => s.portrait);
  const consent = useStudio((s) => s.consent);
  const emotion = useStudio((s) => s.emotion);
  const intensity = useStudio((s) => s.intensity);

  const [phase, setPhase] = useState<"idle" | "running" | "paused" | "lost" | "complete" | "error">("idle");
  const [conn, setConn] = useState<ConnState>("idle");
  const [engineMode, setEngineMode] = useState(false);
  const [hasFrames, setHasFrames] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string>();
  const [stats, setStats] = useState<LiveStats>(EMPTY_STATS);
  const [events, setEvents] = useState<EmotionEvent[]>([]);
  const [frameLog, setFrameLog] = useState<number[]>([]);
  const [exporting, setExporting] = useState(false);

  const engineRef = useRef<EngineSession | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const pendingFrame = useRef<ImageBitmap | HTMLImageElement | null>(null);
  const rafRef = useRef(0);
  const startedAt = useRef(0);
  const statsRef = useRef<LiveStats>(EMPTY_STATS);

  const mic = useMicrophone({
    deviceId: micDeviceId || undefined,
    onPcm: (pcm) => engineRef.current?.sendAudio(pcm),
  });

  const patchStats = useCallback((p: Partial<LiveStats>) => {
    statsRef.current = { ...statsRef.current, ...p };
    setStats(statsRef.current);
  }, []);

  // Draw newest frame once per animation frame; frames replaced before drawing count as dropped.
  const drawLoop = useCallback(() => {
    const f = pendingFrame.current;
    const c = canvasRef.current;
    if (f && c) {
      const ctx = c.getContext("2d");
      ctx?.drawImage(f, 0, 0, c.width, c.height);
      pendingFrame.current = null;
      if ("close" in f) (f as ImageBitmap).close();
      statsRef.current.framesDisplayed++;
    }
    rafRef.current = requestAnimationFrame(drawLoop);
  }, []);

  useEffect(() => {
    rafRef.current = requestAnimationFrame(drawLoop);
    return () => cancelAnimationFrame(rafRef.current);
  }, [drawLoop]);

  // Push stats to UI 4×/s and keep a per-second frame log for the timeline.
  useEffect(() => {
    if (phase !== "running") return;
    let lastCount = statsRef.current.framesReceived;
    const a = window.setInterval(() => setStats({ ...statsRef.current }), 250);
    const b = window.setInterval(() => {
      const n = statsRef.current.framesReceived;
      setFrameLog((l) => [...l, n - lastCount]);
      lastCount = n;
    }, 1000);
    return () => {
      window.clearInterval(a);
      window.clearInterval(b);
    };
  }, [phase]);

  const start = useCallback(async () => {
    const st = studioStore.get();
    const check = canStartSession(st);
    if (!check.ok) {
      toast.error(check.reason);
      return;
    }
    setErrorMsg(undefined);
    setEvents([{ t: 0, emotion: st.emotion, intensity: st.intensity }]);
    setFrameLog([]);
    statsRef.current = { ...EMPTY_STATS };
    setStats(statsRef.current);
    setHasFrames(false);
    startedAt.current = Date.now();

    if (engineUrl) {
      setEngineMode(true);
      const session = new EngineSession(engineUrl, {
        onState: (s, detail) => {
          setConn(s);
          if (s === "lost") {
            setPhase("lost");
            mic.pause();
          }
          if (s === "error") {
            setPhase("error");
            setErrorMsg(detail);
            mic.stop();
          }
        },
        onReady: () => setConn("open"),
        onFrame: (bmp) => {
          statsRef.current.framesReceived++;
          if (pendingFrame.current) statsRef.current.framesDropped++;
          pendingFrame.current = bmp;
          setHasFrames(true);
        },
        onStats: patchStats,
        onDone: () => setPhase("complete"),
      });
      engineRef.current = session;
      const crop = await renderCrop(st.portrait!);
      session.connect({ emotion: st.emotion, intensity: st.intensity, portrait: crop });
    } else {
      setEngineMode(false);
      setConn("idle");
    }
    setPhase("running");
    await mic.start();
  }, [engineUrl, mic, patchStats]);

  const pause = useCallback(() => {
    mic.pause();
    setPhase("paused");
  }, [mic]);

  const resume = useCallback(() => {
    mic.resume();
    setPhase("running");
  }, [mic]);

  const stop = useCallback(() => {
    mic.stop();
    engineRef.current?.stop();
    setPhase("complete");
    setStats({ ...statsRef.current });
    const st = studioStore.get();
    studioStore.set((s) => ({
      sessions: [
        {
          id: `s-${startedAt.current}`,
          avatarName: st.avatarName,
          startedAt: startedAt.current,
          durationMs: mic.elapsed,
          emotionChanges: Math.max(0, events.length - 1),
          finalEmotion: st.emotion,
          finalIntensity: st.intensity,
          engine: engineMode,
          framesReceived: statsRef.current.framesReceived,
        },
        ...s.sessions,
      ],
    }));
  }, [mic, events.length, engineMode]);

  const reset = useCallback(() => {
    engineRef.current?.stop();
    engineRef.current = null;
    mic.reset();
    setPhase("idle");
    setConn("idle");
    setEvents([]);
    setFrameLog([]);
    setHasFrames(false);
    setErrorMsg(undefined);
    statsRef.current = { ...EMPTY_STATS };
    setStats(statsRef.current);
    const c = canvasRef.current;
    c?.getContext("2d")?.clearRect(0, 0, c.width, c.height);
  }, [mic]);

  // Emotion changes during a live session: log on the timeline and forward to the engine.
  const lastSent = useRef<{ e: EmotionId; i: number } | null>(null);
  useEffect(() => {
    if (phase !== "running" && phase !== "paused") return;
    const prev = lastSent.current;
    if (prev && prev.e === emotion && prev.i === intensity) return;
    lastSent.current = { e: emotion, i: intensity };
    const handle = window.setTimeout(() => {
      engineRef.current?.setEmotion(emotion, intensity);
      setEvents((ev) => {
        const t = mic.elapsed;
        const last = ev[ev.length - 1];
        if (last && last.emotion === emotion && Math.abs(last.intensity - intensity) < 1) return ev;
        if (last && t - last.t < 400) return [...ev.slice(0, -1), { t: last.t, emotion, intensity }];
        return [...ev, { t, emotion, intensity }];
      });
    }, 120);
    return () => window.clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [emotion, intensity, phase]);

  useEffect(() => () => engineRef.current?.stop(), []);

  const doExport = useCallback(async () => {
    if (!engineUrl) return;
    setExporting(true);
    try {
      const blob = await exportSession(engineUrl, engineRef.current?.sessionId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `emostream-${startedAt.current}.mp4`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Export downloaded");
    } catch (e) {
      toast.error((e as Error).message || "Export failed");
    } finally {
      setExporting(false);
    }
  }, [engineUrl]);

  let stage: StageState;
  if (!portrait) stage = preparing ? "preparing" : "empty";
  else if (preparing) stage = "preparing";
  else if (phase === "error") stage = "error";
  else if (phase === "lost") stage = "lost";
  else if (phase === "complete") stage = "complete";
  else if (phase === "paused") stage = "paused";
  else if (phase === "running") {
    if (!engineMode) stage = "preview";
    else if (conn === "connecting") stage = "initializing";
    else if (hasFrames) stage = "active";
    else stage = "waiting";
  } else stage = "ready";

  return {
    stage,
    phase,
    conn,
    engineMode,
    engineUrl,
    errorMsg,
    stats,
    events,
    frameLog,
    mic,
    canvasRef,
    canStart: canStartSession({ portrait, consent }),
    exporting,
    start,
    pause,
    resume,
    stop,
    reset,
    doExport,
  };
}

export type StudioSession = ReturnType<typeof useStudioSession>;
