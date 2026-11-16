import { useCallback, useEffect, useRef, useState } from "react";
import { decodeAudioFile, MicCapture, startMicrophone, SyncedVoice } from "./lib/audio";
import { Chunker, CHUNK_SAMPLES, Emotion, EMOTIONS, FPS, ModelName, SAMPLE_RATE, ServerStats } from "./lib/protocol";
import { FramePlayer, h264Supported, PlayerStats } from "./lib/player";
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
  const [play, setPlay] = useState<PlayerStats | null>(null);
  const [roundTrip, setRoundTrip] = useState<number | null>(null);
  const [level, setLevel] = useState(0);
  const [recordingUrl, setRecordingUrl] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [monitor, setMonitor] = useState(false);
  const [net, setNet] = useState<{ pingMs: number | null; kbps: number } | null>(null);
  const voiceRef = useRef<SyncedVoice | null>(null);
  const monitorRef = useRef(false);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const sessionRef = useRef<LiveSession | null>(null);
  const micRef = useRef<MicCapture | null>(null);
  const chunkerRef = useRef(new Chunker(CHUNK_SAMPLES));
  const playbackRef = useRef<{ ctx: AudioContext; t0: number | null; buffer: AudioBuffer; dest: MediaStreamAudioDestinationNode } | null>(null);
  const feedTimer = useRef<number | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const playerRef = useRef<FramePlayer | null>(null);
  const diagLog = useRef<Record<string, unknown>[]>([]);
  const statsRef = useRef<ServerStats | null>(null);
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
      const p = playerRef.current?.stats() ?? null;
      const trip = median(trips.current.slice(-50));
      const sess = sessionRef.current;
      const network = sess ? { pingMs: sess.pingMs, kbps: Math.round(sess.receivedKbps()) } : null;
      if (network) setNet(network);
      if (p) {
        setPlay(p);
        // One row per half second, for the downloadable diagnostics file.
        diagLog.current.push({ t: Math.round(performance.now()), client: p, roundTripMs: trip, network,
          voice: voiceRef.current ? { scheduled: voiceRef.current.scheduled, missed: voiceRef.current.missed } : null,
          server: statsRef.current });
      }
      setRoundTrip(trip);
    }, 500);
    return () => window.clearInterval(id);
  }, [phase]);

  const cleanup = useCallback(async () => {
    if (feedTimer.current !== null) window.clearInterval(feedTimer.current);
    feedTimer.current = null;
    timers.current.forEach((t) => window.clearTimeout(t));
    timers.current = [];
    if (micRef.current) await micRef.current.stop();
    micRef.current = null;
    if (recorderRef.current && recorderRef.current.state !== "inactive") recorderRef.current.stop();
    recorderRef.current = null;
    playerRef.current?.stop();
    playerRef.current = null;
    if (voiceRef.current) await voiceRef.current.close();
    voiceRef.current = null;
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
    setNotice(null);
    setStats(null);
    setRecordingUrl(null);
    trips.current = [];
    diagLog.current = [];
    setPlay(null);
    // Microphone audio is sent every 80 ms so the server is not kept waiting for a full block.
    chunkerRef.current = new Chunker(source === "mic" ? SAMPLE_RATE * 0.08 : CHUNK_SAMPLES);
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
      onReady: (info) => {
        setPhase("live");
        setNotice(info.portrait?.mouth_open
          ? "This photo shows an open mouth, so the avatar's mouth is being closed automatically. A photo with a closed mouth and a relaxed face gives the most natural result."
          : null);
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
        void playerRef.current?.push(frame);
      },
      onStats: (st) => {
        statsRef.current = st;
        setStats(st);
      },
      onDone: (final) => {
        setStats(final);
        const tail = (playerRef.current?.stats().playoutDelayMs ?? 0) + 600; // let buffered frames play out
        window.setTimeout(() => sessionRef.current?.stop(), tail);
      },
      onError: (message) => setError(message),
      onClose: () => void cleanup(),
    });
    sessionRef.current = session;

    // Frames are presented on a 40 ms timeline from a small buffer, not when they arrive.
    const pb = playbackRef.current;
    const player = new FramePlayer(canvasRef.current!, {
      // Live: a small margin on top of the measured network jitter, growing to 1.2 s on a
      // bad link. The voice is played on the same timeline, so delay does not cost sync.
      targetDelayMs: pb ? 350 : 80,
      maxDelayMs: pb ? 600 : 1200,
      synced: !!pb,
      onNeedKeyFrame: () => sessionRef.current?.requestKeyFrame(),
      onTimeline: (frameZeroTime) => {
        if (!pb) return;
        // Uploaded audio: start the sound exactly when frame 0 is shown, and keep the
        // picture locked to the audio clock from then on.
        const src = pb.ctx.createBufferSource();
        src.buffer = pb.buffer;
        src.connect(pb.ctx.destination);
        src.connect(pb.dest);
        const startAt = pb.ctx.currentTime + Math.max(0, frameZeroTime - performance.now()) / 1000;
        src.start(startAt);
        player.audioClockMs = () => (pb.ctx.currentTime - startAt) * 1000;
        startRecording(pb.dest.stream);
      },
    });
    playerRef.current = player;
    player.start();
    // Handles for the measurement scripts in evaluation/benchmarks (read-only use).
    (window as unknown as Record<string, unknown>).__emostream = { player, voice: () => voiceRef.current };

    try {
      if (source === "mic") {
        // The avatar's voice: the same audio, played and recorded in step with the picture.
        const voice = new SyncedVoice(() => playerRef.current?.timelineBase ?? null);
        voice.setMonitor(monitorRef.current);
        voiceRef.current = voice;
        micRef.current = await startMicrophone(
          (block) => chunkerRef.current.push(block).forEach((c) => {
            const first = session.sendAudio(c);
            if (first >= 0) voice.push(first, c);
          }),
          setLevel,
        );
        startRecording(voice.recordStream);
      }
      // "?video=jpeg" forces the old picture-per-frame transport, for comparisons.
      const forced = new URLSearchParams(location.search).get("video");
      const video = forced !== "jpeg" && (await h264Supported()) ? "h264" : "jpeg";
      session.open(await portrait.arrayBuffer(), { sampleRate: SAMPLE_RATE, emotion, intensity, model, size: 512, video, bitrateKbps: 900 });
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
      if (rest) {
        const first = session.sendAudio(rest);
        if (first >= 0) voiceRef.current?.push(first, rest);
      }
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

  const chooseMonitor = (on: boolean) => {
    setMonitor(on);
    monitorRef.current = on;
    voiceRef.current?.setMonitor(on);
  };

  const downloadDiagnostics = () => {
    const blob = new Blob([JSON.stringify({ source, model, emotion, intensity, userAgent: navigator.userAgent, rows: diagLog.current }, null, 1)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "emostream-diagnostics.json";
    a.click();
    URL.revokeObjectURL(a.href);
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
          {notice && <p className="notice">{notice}</p>}
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
            {source === "mic" && (
              <label className="check"><input type="checkbox" checked={monitor} onChange={(e) => chooseMonitor(e.target.checked)} />
                Hear the avatar's voice, in step with its lips (use headphones).</label>
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
              <div><dt>Frames shown</dt><dd>{fmt(play?.presentedFps, 1)}<small> per second, on screen</small></dd></div>
              <div><dt>Avatar behind you</dt><dd>{fmt(roundTrip === null ? null : roundTrip + (play?.playoutDelayMs ?? 0))}<small> ms; its voice and lips stay together</small></dd></div>
              <div><dt>Network round trip</dt><dd>{fmt(net?.pingMs)}<small> ms</small></dd></div>
              <div><dt>Video stream</dt><dd>{net ? net.kbps : "–"}<small> kbit/s {play?.codec === "h264" ? "H.264" : play?.codec === "jpeg" ? "JPEG" : ""}</small></dd></div>
              <div><dt>Server delay</dt><dd>{fmt(stats?.latency?.p50_ms)}<small> ms median</small></dd></div>
              <div><dt>Slowest 5%</dt><dd>{fmt(stats?.latency?.p95_ms)}<small> ms</small></dd></div>
              <div><dt>Frames skipped</dt><dd>{stats ? stats.frames_dropped : "–"}<small> of {stats ? stats.frames : "–"}</small></dd></div>
              <div><dt>GPU memory</dt><dd>{fmt(stats?.gpu?.torch_reserved_gib, 2)}<small> GiB reserved</small></dd></div>
            </dl>
            {play && (
              <details className="diag">
                <summary>Playback diagnostics</summary>
                <dl>
                  <div><dt>Received / shown per second</dt><dd>{fmt(play.receivedFps, 1)} / {fmt(play.presentedFps, 1)}</dd></div>
                  <div><dt>Time between shown frames, median / 95% / longest</dt><dd>{fmt(play.intervalP50Ms)} / {fmt(play.intervalP95Ms)} / {fmt(play.intervalMaxMs)} ms</dd></div>
                  <div><dt>Frame age when shown, median / 95%</dt><dd>{fmt(play.ageP50Ms)} / {fmt(play.ageP95Ms)} ms</dd></div>
                  <div><dt>Buffer</dt><dd>{play.bufferDepth} frames, {fmt(play.playoutDelayMs)} ms delay, moved {play.timelineShifts}×</dd></div>
                  <div><dt>Arrival jitter (95%)</dt><dd>{fmt(play.jitterP95Ms)} ms</dd></div>
                  <div><dt>Voice to frame arrival</dt><dd>{fmt(roundTrip)} ms</dd></div>
                  <div><dt>Server: sent / target bitrate</dt><dd>{fmt(stats?.video?.sent_kbps)} / {fmt(stats?.video?.target_kbps)} kbit/s</dd></div>
                  <div><dt>Server: frames held back for the network</dt><dd>{stats?.video?.frames_skipped_for_network ?? "–"}, backlog {stats?.video?.backlog_ms ?? "–"} ms, {stats?.video?.congestion_events ?? "–"} slow-downs</dd></div>
                  <div><dt>Your audio reaching the server late (95% / worst)</dt><dd>{fmt(stats?.uplink?.lag_p95_ms)} / {fmt(stats?.uplink?.lag_max_ms)} ms</dd></div>
                  <div><dt>Decoder errors</dt><dd>{play.decodeErrors}</dd></div>
                  <div><dt>Late / skipped / overflow / held</dt><dd>{play.droppedLate} / {play.skipped} / {play.droppedOverflow} / {play.holds}</dd></div>
                  <div><dt>Out of order / duplicate</dt><dd>{play.outOfOrder} / {play.duplicates}</dd></div>
                  <div><dt>Decode time, median</dt><dd>{fmt(play.decodeP50Ms, 1)} ms</dd></div>
                  <div><dt>Picture ahead of sound</dt><dd>{fmt(play.avOffsetMs)} ms</dd></div>
                  <div><dt>Server queue</dt><dd>{stats?.queued_chunks ?? "–"} chunks</dd></div>
                </dl>
                <button className="secondary" onClick={downloadDiagnostics}>Save diagnostics file</button>
              </details>
            )}
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
