import { useCallback, useEffect, useRef, useState } from "react";
import { decodeAudioFile, MicCapture, startMicrophone } from "./lib/audio";
import { Chunker, CHUNK_SAMPLES, Emotion, EMOTIONS, FPS, ModelName, SAMPLE_RATE, ServerStats } from "./lib/protocol";
import { LiveSession } from "./lib/session";

type Phase = "idle" | "connecting" | "live" | "finishing";
type Source = "mic" | "file";

const EMOTION_LABEL: Record<Emotion, string> = {
  neutral: "Neutral",
  happy: "Happy",
  sad: "Sad",
  angry: "Angry",
  surprised: "Surprised",
};

function median(xs: number[]): number | null {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.floor(s.length / 2)];
}

export default function App() {
  const [portrait, setPortrait] = useState<File | null>(null);
  const [portraitUrl, setPortraitUrl] = useState<string | null>(null);
  const [consentPortrait, setConsentPortrait] = useState(false);
  const [consentAudio, setConsentAudio] = useState(false);
  const [source, setSource] = useState<Source>("mic");
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [emotion, setEmotion] = useState<Emotion>("neutral");
  const [intensity, setIntensity] = useState(0.7);
  const [model, setModel] = useState<ModelName>("emostream");
  const [models, setModels] = useState<ModelName[]>(["emostream", "ditto"]);
  const [gpu, setGpu] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<ServerStats | null>(null);
  const [shownFps, setShownFps] = useState<number | null>(null);
  const [roundTrip, setRoundTrip] = useState<number | null>(null);
  const [level, setLevel] = useState(0);
  const [recordingUrl, setRecordingUrl] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const sessionRef = useRef<LiveSession | null>(null);
  const micRef = useRef<MicCapture | null>(null);
  const chunkerRef = useRef(new Chunker(CHUNK_SAMPLES));
  const playbackRef = useRef<{ ctx: AudioContext; t0: number | null; buffer: AudioBuffer; dest: MediaStreamAudioDestinationNode } | null>(null);
  const feedTimer = useRef<number | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const drawTimes = useRef<number[]>([]);
  const trips = useRef<number[]>([]);
  const timers = useRef<number[]>([]);

  useEffect(() => {
    fetch("/api/info")
      .then((r) => (r.ok ? r.json() : null))
      .then((info) => {
        if (!info) return;
        setGpu(info.gpu ?? null);
        if (Array.isArray(info.models) && info.models.length) {
          setModels(info.models);
          setModel(info.models[0]);
        }
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!portrait) {
      setPortraitUrl(null);
      return;
    }
    const url = URL.createObjectURL(portrait);
    setPortraitUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [portrait]);

  // Client-side numbers, refreshed twice a second while a session runs.
  useEffect(() => {
    if (phase === "idle") return;
    const id = window.setInterval(() => {
      const now = performance.now();
      drawTimes.current = drawTimes.current.filter((t) => now - t < 2000);
      setShownFps(drawTimes.current.length / 2);
      setRoundTrip(median(trips.current.slice(-50)));
    }, 500);
    return () => window.clearInterval(id);
  }, [phase]);

  const draw = useCallback(async (jpeg: Uint8Array) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const bitmap = await createImageBitmap(new Blob([jpeg as BlobPart], { type: "image/jpeg" }));
    if (canvas.width !== bitmap.width) {
      canvas.width = bitmap.width;
      canvas.height = bitmap.height;
    }
    canvas.getContext("2d")!.drawImage(bitmap, 0, 0);
    bitmap.close();
    drawTimes.current.push(performance.now());
  }, []);

  const cleanup = useCallback(async () => {
    if (feedTimer.current !== null) window.clearInterval(feedTimer.current);
    feedTimer.current = null;
    timers.current.forEach((t) => window.clearTimeout(t));
    timers.current = [];
    if (micRef.current) await micRef.current.stop();
    micRef.current = null;
    if (recorderRef.current && recorderRef.current.state !== "inactive") recorderRef.current.stop();
    recorderRef.current = null;
    if (playbackRef.current) await playbackRef.current.ctx.close().catch(() => undefined);
    playbackRef.current = null;
    sessionRef.current = null;
    setLevel(0);
    setPhase("idle");
  }, []);

  const startRecording = (audioStream: MediaStream | null) => {
    const canvas = canvasRef.current;
    if (!canvas || typeof MediaRecorder === "undefined") return;
    const stream = canvas.captureStream(FPS);
    audioStream?.getAudioTracks().forEach((t) => stream.addTrack(t));
    const chunks: Blob[] = [];
    const rec = new MediaRecorder(stream);
    rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    rec.onstop = () => setRecordingUrl(URL.createObjectURL(new Blob(chunks, { type: rec.mimeType || "video/webm" })));
    rec.start(500);
    recorderRef.current = rec;
  };

  const start = async () => {
    if (!portrait || !consentPortrait || !consentAudio) return;
    setError(null);
    setStats(null);
    setRecordingUrl(null);
    trips.current = [];
    drawTimes.current = [];
    chunkerRef.current = new Chunker(CHUNK_SAMPLES);
    setPhase("connecting");

    let fileSamples: Float32Array | null = null;
    try {
      if (source === "file") {
        if (!audioFile) throw new Error("Choose an audio file first.");
        const decoded = await decodeAudioFile(audioFile);
        fileSamples = decoded.samples;
        const ctx = new AudioContext();
        playbackRef.current = { ctx, t0: null, buffer: decoded.buffer, dest: ctx.createMediaStreamDestination() };
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "The audio file could not be read.");
      setPhase("idle");
      return;
    }

    const session = new LiveSession({
      onReady: () => {
        setPhase("live");
        if (fileSamples) {
          // Deliver the file at the pace a microphone would.
          const samples = fileSamples;
          let pos = 0;
          const began = performance.now();
          feedTimer.current = window.setInterval(() => {
            const due = Math.min(samples.length, Math.floor(((performance.now() - began) / 1000) * SAMPLE_RATE));
            while (pos + CHUNK_SAMPLES <= due) {
              session.sendAudio(samples.subarray(pos, pos + CHUNK_SAMPLES));
              pos += CHUNK_SAMPLES;
            }
            if (due >= samples.length) {
              if (pos < samples.length) session.sendAudio(samples.subarray(pos));
              pos = samples.length;
              window.clearInterval(feedTimer.current!);
              feedTimer.current = null;
              setPhase("finishing");
              session.end();
            }
          }, 50);
        }
      },
      onFrame: (frame, trip) => {
        if (trip !== null) trips.current.push(trip);
        const pb = playbackRef.current;
        if (!pb) {
          void draw(frame.jpeg); // microphone: show as soon as it arrives
          return;
        }
        // File: start the sound with the first frame and hold every frame to its timestamp.
        if (pb.t0 === null) {
          pb.t0 = performance.now() - frame.index * (1000 / FPS);
          const src = pb.ctx.createBufferSource();
          src.buffer = pb.buffer;
          src.connect(pb.ctx.destination);
          src.connect(pb.dest);
          src.start(0, frame.index / FPS);
          startRecording(pb.dest.stream);
        }
        const wait = pb.t0 + frame.index * (1000 / FPS) - performance.now();
        if (wait <= 2) void draw(frame.jpeg);
        else timers.current.push(window.setTimeout(() => void draw(frame.jpeg), wait));
      },
      onStats: setStats,
      onDone: (final) => {
        setStats(final);
        const tail = playbackRef.current ? 600 : 0; // let scheduled frames play out
        window.setTimeout(() => sessionRef.current?.stop(), tail);
      },
      onError: (message) => setError(message),
      onClose: () => void cleanup(),
    });
    sessionRef.current = session;

    try {
      if (source === "mic") {
        micRef.current = await startMicrophone(
          (block) => chunkerRef.current.push(block).forEach((c) => session.sendAudio(c)),
          setLevel,
        );
        startRecording(micRef.current.stream);
      }
      session.open(await portrait.arrayBuffer(), { sampleRate: SAMPLE_RATE, emotion, intensity, model, size: 512 });
    } catch (e) {
      const denied = e instanceof DOMException && (e.name === "NotAllowedError" || e.name === "SecurityError");
      setError(denied ? "Microphone access was blocked. Allow it in the browser's site settings and start again."
        : e instanceof Error ? e.message : "The session could not start.");
      session.stop();
      await cleanup();
    }
  };

  const stop = () => {
    const session = sessionRef.current;
    if (!session) return;
    if (source === "mic" && phase === "live") {
      // Send what is left, then let the server finish the last frames.
      void micRef.current?.stop();
      micRef.current = null;
      const rest = chunkerRef.current.flush();
      if (rest) session.sendAudio(rest);
      setPhase("finishing");
      session.end();
    } else {
      session.stop();
    }
  };

  const chooseEmotion = (e: Emotion) => {
    setEmotion(e);
    sessionRef.current?.setEmotion(e, intensity);
  };
  const chooseIntensity = (v: number) => {
    setIntensity(v);
    sessionRef.current?.setEmotion(emotion, v);
  };

  const exportMp4 = async () => {
    if (!portrait || !audioFile) return;
    setExporting(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("portrait", portrait);
      form.append("audio", audioFile);
      form.append("emotion", emotion);
      form.append("intensity", String(intensity));
      form.append("model", model);
      form.append("portrait_consent", "true");
      form.append("audio_consent", "true");
      const r = await fetch("/api/export", { method: "POST", body: form });
      if (!r.ok) {
        const body = await r.json().catch(() => null);
        throw new Error(body?.detail?.message ?? `Export failed (${r.status}).`);
      }
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = "emostream.mp4";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed.");
    } finally {
      setExporting(false);
    }
  };

  const busy = phase !== "idle";
  const consented = consentPortrait && consentAudio;
  const canStart = !!portrait && consented && !busy && (source === "mic" || !!audioFile);
  const blocker = !portrait ? "Add a portrait to begin."
    : !consented ? "Confirm both permissions to continue."
    : source === "file" && !audioFile ? "Choose an audio file." : null;
  const fmt = (v: number | null | undefined, digits = 0, unit = "") => (v === null || v === undefined || Number.isNaN(v) ? "–" : `${v.toFixed(digits)}${unit}`);
  const ring = { ["--ring" as string]: `var(--emo-${emotion})`, ["--weight" as string]: emotion === "neutral" ? 0.25 : 0.25 + 0.75 * intensity };

  return (
    <div className="app">
      <header className="masthead">
        <h1>EmoStream</h1>
        <p>One portrait and your voice become a talking, expressive avatar.</p>
      </header>

      <main className="layout">
        <section className={`stage ${busy ? "is-live" : ""}`} style={ring} aria-label="Avatar">
          <div className="frame">
            <canvas ref={canvasRef} width={512} height={512} className={busy || stats ? "shown" : ""} />
            {!busy && !stats && (portraitUrl
              ? <img src={portraitUrl} alt="Your portrait" />
              : <div className="empty"><p>Your portrait appears here.</p></div>)}
            {phase === "connecting" && <div className="veil">Preparing the avatar…</div>}
            {phase === "finishing" && <div className="veil veil-quiet">Finishing the last frames…</div>}
          </div>
          <div className="meter" aria-hidden="true"><span style={{ width: `${Math.min(100, level * 400)}%` }} /></div>
          <div className="stage-actions">
            {!busy
              ? <button className="primary" onClick={start} disabled={!canStart}>{source === "mic" ? "Start speaking" : "Play through the avatar"}</button>
              : <button className="primary stop" onClick={stop} disabled={phase !== "live"}>Stop</button>}
            {!busy && blocker && <span className="hint">{blocker}</span>}
            {recordingUrl && !busy && <a className="link" href={recordingUrl} download="emostream-session.webm">Save this session</a>}
          </div>
          {error && <p className="error" role="alert">{error}</p>}
        </section>

        <section className="console">
          <fieldset disabled={busy}>
            <legend>Portrait</legend>
            <label className="file">
              <input type="file" accept="image/png,image/jpeg,image/webp" onChange={(e) => setPortrait(e.target.files?.[0] ?? null)} />
              <span>{portrait ? portrait.name : "Choose a photo of one face, looking at the camera"}</span>
            </label>
            <label className="check"><input type="checkbox" checked={consentPortrait} onChange={(e) => setConsentPortrait(e.target.checked)} />
              The person in this photo has agreed to be animated.</label>
            <label className="check"><input type="checkbox" checked={consentAudio} onChange={(e) => setConsentAudio(e.target.checked)} />
              The voice is mine, or the speaker has agreed to its use.</label>
            <p className="note">Photos and audio are processed for the session and not kept. Every frame is marked “AI-generated”.</p>
          </fieldset>

          <fieldset disabled={busy}>
            <legend>Voice</legend>
            <div className="segmented" role="radiogroup" aria-label="Voice source">
              <button role="radio" aria-checked={source === "mic"} onClick={() => setSource("mic")}>Microphone</button>
              <button role="radio" aria-checked={source === "file"} onClick={() => setSource("file")}>Audio file</button>
            </div>
            {source === "file" && (
              <>
                <label className="file">
                  <input type="file" accept="audio/*" onChange={(e) => setAudioFile(e.target.files?.[0] ?? null)} />
                  <span>{audioFile ? audioFile.name : "Choose a recording of speech"}</span>
                </label>
                <button className="secondary" onClick={exportMp4} disabled={!portrait || !audioFile || !consented || exporting}>
                  {exporting ? "Rendering…" : "Download as MP4"}
                </button>
              </>
            )}
            {models.length > 1 && (
              <label className="select">Motion model
                <select value={model} onChange={(e) => setModel(e.target.value as ModelName)}>
                  {models.includes("emostream") && <option value="emostream">EmoStream (ours, low delay)</option>}
                  {models.includes("ditto") && <option value="ditto">Ditto (pretrained baseline)</option>}
                </select>
              </label>
            )}
          </fieldset>

          <fieldset>
            <legend>Emotion</legend>
            <div className="emotions" role="radiogroup" aria-label="Emotion">
              {EMOTIONS.map((e) => (
                <button key={e} role="radio" aria-checked={emotion === e} className={`emo emo-${e}`} onClick={() => chooseEmotion(e)}>
                  {EMOTION_LABEL[e]}
                </button>
              ))}
            </div>
            <label className="slider">
              <span>Intensity <output>{Math.round(intensity * 100)}%</output></span>
              <input type="range" min={0} max={1} step={0.05} value={intensity} disabled={emotion === "neutral"}
                onChange={(e) => chooseIntensity(Number(e.target.value))} />
            </label>
            <p className="note">Change either while speaking; the face follows within a moment.</p>
          </fieldset>

          <fieldset>
            <legend>Performance</legend>
            <dl className="numbers">
              <div><dt>Frames shown</dt><dd>{fmt(shownFps, 1)}<small> per second</small></dd></div>
              <div><dt>Voice to face</dt><dd>{fmt(roundTrip)}<small> ms, in this browser</small></dd></div>
              <div><dt>Server delay</dt><dd>{fmt(stats?.latency?.p50_ms)}<small> ms median</small></dd></div>
              <div><dt>Slowest 5%</dt><dd>{fmt(stats?.latency?.p95_ms)}<small> ms</small></dd></div>
              <div><dt>Frames skipped</dt><dd>{stats ? stats.frames_dropped : "–"}<small> of {stats ? stats.frames : "–"}</small></dd></div>
              <div><dt>GPU memory</dt><dd>{fmt(stats?.gpu?.torch_reserved_gib, 2)}<small> GiB reserved</small></dd></div>
            </dl>
            {stats?.stages_ms && (
              <p className="note">
                Per frame: motion {fmt(stats.stages_ms.behaviour, 1)} ms, rendering {fmt(stats.stages_ms.render, 1)} ms.
                {gpu ? ` Running on ${gpu}.` : ""}
              </p>
            )}
          </fieldset>
        </section>
      </main>
    </div>
  );
}
