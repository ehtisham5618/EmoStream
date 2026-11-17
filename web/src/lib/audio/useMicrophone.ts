import { useCallback, useEffect, useRef, useState } from "react";
import { startMicrophone, type MicCapture } from "@engine/audio";

export type MicState = "idle" | "requesting" | "denied" | "recording" | "paused" | "stopped" | "error" | "unsupported";
export type MicPermission = "unknown" | "prompt" | "granted" | "denied";

const HISTORY = 240;

/**
 * Real microphone capture: device list, permission, level meter, waveform history, and 16 kHz
 * mono float blocks from the engine's reference capture path (AudioWorklet, `@engine/audio`).
 * Blocks are delivered only while recording; nothing is buffered while paused.
 */
export function useMicrophone(opts: { deviceId?: string | undefined; onSamples?: ((samples: Float32Array) => void) | undefined } = {}) {
  const [state, setState] = useState<MicState>("idle");
  const [permission, setPermission] = useState<MicPermission>("unknown");
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [level, setLevel] = useState(0);
  const [history, setHistory] = useState<number[]>([]);
  /** Every 50 ms level sample since start (whole session). */
  const logRef = useRef<number[]>([]);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string>();

  const capRef = useRef<MicCapture | null>(null);
  const rmsRef = useRef(0);
  const timerRef = useRef(0);
  const startedRef = useRef(0);
  const accRef = useRef(0);
  const pausedRef = useRef(false);
  const onSamplesRef = useRef(opts.onSamples);
  onSamplesRef.current = opts.onSamples;

  const refreshDevices = useCallback(async () => {
    if (!navigator.mediaDevices?.enumerateDevices) return;
    const all = await navigator.mediaDevices.enumerateDevices();
    setDevices(all.filter((d) => d.kind === "audioinput"));
  }, []);

  useEffect(() => {
    if (!navigator.mediaDevices?.getUserMedia) {
      setState("unsupported");
      return;
    }
    refreshDevices();
    navigator.mediaDevices.addEventListener?.("devicechange", refreshDevices);
    let status: PermissionStatus | undefined;
    navigator.permissions
      ?.query({ name: "microphone" as PermissionName })
      .then((s) => {
        status = s;
        setPermission(s.state as MicPermission);
        s.onchange = () => setPermission(s.state as MicPermission);
      })
      .catch(() => setPermission("unknown"));
    return () => {
      navigator.mediaDevices.removeEventListener?.("devicechange", refreshDevices);
      if (status) status.onchange = null;
    };
  }, [refreshDevices]);

  const teardown = useCallback(() => {
    window.clearInterval(timerRef.current);
    const cap = capRef.current;
    capRef.current = null;
    void cap?.stop().catch(() => undefined);
  }, []);

  useEffect(() => teardown, [teardown]);

  const fail = useCallback((e: unknown) => {
    const name = (e as DOMException)?.name;
    if (name === "NotAllowedError" || name === "SecurityError") {
      setPermission("denied");
      setState("denied");
      setError("Microphone access was blocked. Allow it in your browser's site settings, then try again.");
    } else if (name === "NotFoundError" || name === "OverconstrainedError") {
      setState("error");
      setError("That microphone isn't available. Pick another input.");
    } else {
      setState("error");
      setError("The microphone couldn't start.");
    }
  }, []);

  /**
   * Asks for microphone permission without capturing anything, so a refusal is known before an
   * engine session is opened. Resolves true when access is allowed.
   */
  const probe = useCallback(async (): Promise<boolean> => {
    setError(undefined);
    if (!navigator.mediaDevices?.getUserMedia) {
      setState("unsupported");
      return false;
    }
    setState("requesting");
    try {
      const s = await navigator.mediaDevices.getUserMedia({
        audio: opts.deviceId ? { deviceId: { exact: opts.deviceId } } : true,
      });
      s.getTracks().forEach((t) => t.stop());
      setPermission("granted");
      setState("idle");
      refreshDevices();
      return true;
    } catch (e) {
      fail(e);
      return false;
    }
  }, [opts.deviceId, refreshDevices, fail]);

  const start = useCallback(async (): Promise<boolean> => {
    setError(undefined);
    setState("requesting");
    try {
      const cap = await startMicrophone(
        (block) => {
          if (!pausedRef.current) onSamplesRef.current?.(block);
        },
        (rms) => {
          rmsRef.current = rms;
        },
        opts.deviceId ? { deviceId: opts.deviceId } : {},
      );
      capRef.current = cap;
      setPermission("granted");
      refreshDevices();
      accRef.current = 0;
      startedRef.current = performance.now();
      pausedRef.current = false;
      setHistory([]);
      logRef.current = [];
      setElapsed(0);
      timerRef.current = window.setInterval(() => {
        if (pausedRef.current) return;
        const v = Math.min(1, Math.pow(rmsRef.current * 4, 0.7));
        setLevel(v);
        logRef.current.push(v);
        setHistory((h) => (h.length >= HISTORY ? [...h.slice(1), v] : [...h, v]));
        setElapsed(accRef.current + performance.now() - startedRef.current);
      }, 50);
      setState("recording");
      return true;
    } catch (e) {
      teardown();
      fail(e);
      return false;
    }
  }, [opts.deviceId, refreshDevices, teardown, fail]);

  const pause = useCallback(() => {
    if (!capRef.current || pausedRef.current) return;
    pausedRef.current = true;
    accRef.current += performance.now() - startedRef.current;
    setLevel(0);
    setState("paused");
  }, []);

  const resume = useCallback(() => {
    if (!capRef.current || !pausedRef.current) return;
    pausedRef.current = false;
    startedRef.current = performance.now();
    setState("recording");
  }, []);

  const stop = useCallback(() => {
    if (capRef.current && !pausedRef.current) accRef.current += performance.now() - startedRef.current;
    pausedRef.current = false;
    setElapsed(accRef.current);
    teardown();
    setLevel(0);
    setState("stopped");
  }, [teardown]);

  const reset = useCallback(() => {
    teardown();
    pausedRef.current = false;
    logRef.current = [];
    setHistory([]);
    setElapsed(0);
    setLevel(0);
    setState("idle");
  }, [teardown]);

  return { state, permission, devices, level, history, log: logRef.current, elapsed, error, probe, start, pause, resume, stop, reset, refreshDevices };
}
