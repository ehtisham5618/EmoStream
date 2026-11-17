import { useCallback, useEffect, useRef, useState } from "react";

export type MicState = "idle" | "requesting" | "denied" | "recording" | "paused" | "stopped" | "error" | "unsupported";
export type MicPermission = "unknown" | "prompt" | "granted" | "denied";

const HISTORY = 240;
const TARGET_RATE = 16000;

/** Real microphone capture: device list, permission, level meter, waveform history and 16 kHz PCM chunks. */
export function useMicrophone(opts: { deviceId?: string | undefined; onPcm?: ((pcm: Int16Array) => void) | undefined } = {}) {
  const [state, setState] = useState<MicState>("idle");
  const [permission, setPermission] = useState<MicPermission>("unknown");
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [level, setLevel] = useState(0);
  const [history, setHistory] = useState<number[]>([]);
  /** Every 50 ms level sample since start (whole session). */
  const logRef = useRef<number[]>([]);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string>();

  const streamRef = useRef<MediaStream | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const procRef = useRef<ScriptProcessorNode | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const timerRef = useRef(0);
  const startedRef = useRef(0);
  const accRef = useRef(0);
  const pausedRef = useRef(false);
  const onPcmRef = useRef(opts.onPcm);
  onPcmRef.current = opts.onPcm;

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
    procRef.current?.disconnect();
    analyserRef.current?.disconnect();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    ctxRef.current?.close().catch(() => {});
    procRef.current = null;
    analyserRef.current = null;
    streamRef.current = null;
    ctxRef.current = null;
  }, []);

  useEffect(() => teardown, [teardown]);

  const start = useCallback(async () => {
    setError(undefined);
    setState("requesting");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { ...(opts.deviceId ? { deviceId: { exact: opts.deviceId } } : {}), echoCancellation: true, noiseSuppression: true },
      });
      setPermission("granted");
      refreshDevices();
      streamRef.current = stream;
      const ctx = new AudioContext();
      ctxRef.current = ctx;
      const src = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 1024;
      analyserRef.current = analyser;
      const proc = ctx.createScriptProcessor(4096, 1, 1);
      procRef.current = proc;
      const ratio = ctx.sampleRate / TARGET_RATE;
      proc.onaudioprocess = (e) => {
        if (pausedRef.current || !onPcmRef.current) return;
        const input = e.inputBuffer.getChannelData(0);
        const outLen = Math.floor(input.length / ratio);
        const out = new Int16Array(outLen);
        for (let i = 0; i < outLen; i++) {
          const s = Math.max(-1, Math.min(1, input[Math.floor(i * ratio)] ?? 0));
          out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
        }
        onPcmRef.current(out);
      };
      src.connect(analyser);
      src.connect(proc);
      proc.connect(ctx.destination);

      const buf = new Float32Array(analyser.fftSize);
      accRef.current = 0;
      startedRef.current = performance.now();
      pausedRef.current = false;
      setHistory([]);
      logRef.current = [];
      setElapsed(0);
      timerRef.current = window.setInterval(() => {
        if (pausedRef.current) return;
        analyser.getFloatTimeDomainData(buf);
        let sum = 0;
        for (const x of buf) sum += x * x;
        const rms = Math.sqrt(sum / buf.length);
        const v = Math.min(1, Math.pow(rms * 4, 0.7));
        setLevel(v);
        logRef.current.push(v);
        setHistory((h) => (h.length >= HISTORY ? [...h.slice(1), v] : [...h, v]));
        setElapsed(accRef.current + performance.now() - startedRef.current);
      }, 50);
      setState("recording");
    } catch (e) {
      teardown();
      const name = (e as DOMException).name;
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
    }
  }, [opts.deviceId, refreshDevices, teardown]);

  const pause = useCallback(() => {
    if (!ctxRef.current) return;
    pausedRef.current = true;
    accRef.current += performance.now() - startedRef.current;
    ctxRef.current.suspend();
    setLevel(0);
    setState("paused");
  }, []);

  const resume = useCallback(() => {
    if (!ctxRef.current) return;
    pausedRef.current = false;
    startedRef.current = performance.now();
    ctxRef.current.resume();
    setState("recording");
  }, []);

  const stop = useCallback(() => {
    if (pausedRef.current === false && ctxRef.current) accRef.current += performance.now() - startedRef.current;
    setElapsed(accRef.current);
    teardown();
    setLevel(0);
    setState("stopped");
  }, [teardown]);

    const reset = useCallback(() => {
    teardown();
    logRef.current = [];
    setHistory([]);
    setElapsed(0);
    setLevel(0);
    setState("idle");
  }, [teardown]);

  return { state, permission, devices, level, history, log: logRef.current, elapsed, error, start, pause, resume, stop, reset, refreshDevices };
}
