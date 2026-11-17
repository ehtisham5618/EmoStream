import { AlertTriangle, CheckCircle2, Expand, Loader2, Minimize, RefreshCw, Unplug, WifiOff } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { CropGuides } from "@/components/brand/HeroStage";
import { FaceMesh } from "@/components/brand/FaceMesh";
import { NEUTRAL_FACE, emotionById } from "@/lib/emotions";
import { frameNo, timecode } from "@/lib/format";
import { useSettings } from "@/lib/settings";
import { cropStyle, useStudio } from "@/lib/studio-store";
import { cn } from "@/lib/utils";
import type { StudioSession } from "./useStudioSession";

export function AvatarStage({ s }: { s: StudioSession }) {
  const portrait = useStudio((x) => x.portrait);
  const emotion = useStudio((x) => x.emotion);
  const intensity = useStudio((x) => x.intensity);
  const name = useStudio((x) => x.avatarName);
  const showGuides = useSettings((x) => x.showCropGuides);
  const showInfo = useSettings((x) => x.showFrameInfo);
  const wrap = useRef<HTMLDivElement>(null);
  const [full, setFull] = useState(false);

  useEffect(() => {
    const on = () => setFull(document.fullscreenElement === wrap.current);
    document.addEventListener("fullscreenchange", on);
    return () => document.removeEventListener("fullscreenchange", on);
  }, []);

  const toggleFull = () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else wrap.current?.requestFullscreen?.();
  };

  const emo = emotionById(emotion);
  const st = s.stage;
  const rendering = st === "active" || (s.engineMode && (st === "paused" || st === "complete") && s.stats.framesReceived > 0);

  return (
    <div ref={wrap} className={cn("stage grain relative flex flex-col overflow-hidden rounded-xl", full && "rounded-none")}>
      {/* top bar */}
      <div className="relative z-[3] flex items-center gap-3 border-b border-stage-line px-4 py-2.5">
        <StateChip state={st} />
        <span className="hidden truncate text-[12.5px] text-stage-muted sm:block">{portrait ? name : "No avatar yet"}</span>
        <span className="ml-auto timecode text-[11px] text-stage-foreground/80">{timecode(s.mic.elapsed)}</span>
        <button
          onClick={toggleFull}
          className="inline-flex size-8 items-center justify-center rounded-md text-stage-foreground/80 hover:bg-stage-foreground/10"
          aria-label={full ? "Exit fullscreen" : "Fullscreen preview"}
        >
          {full ? <Minimize className="size-4" /> : <Expand className="size-4" />}
        </button>
      </div>

      <div className={cn("relative z-[2] flex flex-1 items-center justify-center p-4 sm:p-6", full && "p-8")}>
        <div className={cn("relative aspect-square w-full overflow-hidden rounded-[6px] bg-stage-raised ring-1 ring-stage-line", full ? "max-h-[calc(100vh-9rem)] max-w-[calc(100vh-9rem)]" : "max-w-[min(100%,62vh)]")}>
          {/* static portrait underneath — never animated by the frontend */}
          {portrait && <img src={portrait.url} alt="" style={cropStyle(portrait)} className={cn("transition-opacity duration-500", rendering ? "opacity-0" : st === "ready" ? "opacity-90" : "opacity-45")} draggable={false} />}
          {/* engine frames */}
          <canvas ref={s.canvasRef} width={512} height={512} className={cn("absolute inset-0 h-full w-full", rendering ? "opacity-100" : "opacity-0")} />

          {!portrait && st !== "preparing" && (
            <div className="absolute inset-0 flex items-center justify-center">
              <FaceMesh params={NEUTRAL_FACE} className="h-[86%] w-[86%] text-stage-foreground/25" lineClass="stroke-stage-foreground/25" dotClass="fill-stage-foreground/25" accentClass="stroke-stage-foreground/30" />
            </div>
          )}
          {showGuides && <CropGuides />}

          {/* frame info */}
          {showInfo && (
            <div className="timecode absolute left-3 top-3 flex flex-col gap-0.5 rounded-[3px] bg-stage/70 px-2 py-1 text-[10px] text-stage-foreground/85 backdrop-blur-sm">
              <span>F {frameNo(s.stats.framesDisplayed)} · 512×512</span>
              <span className="text-stage-muted">{s.stats.fps !== undefined ? `${s.stats.fps.toFixed(1)} fps` : "fps —"}</span>
            </div>
          )}

          {/* AI watermark: always visible */}
          <span className="eyebrow pointer-events-none absolute bottom-3 right-3 rounded-[3px] bg-stage/70 px-2 py-1 text-[9px] text-stage-foreground/90 backdrop-blur-sm">
            AI-generated · EmoStream
          </span>

          <StageOverlay s={s} hasPortrait={!!portrait} />
        </div>
      </div>

      {/* bottom strip */}
      <div className="relative z-[3] flex flex-wrap items-center gap-x-5 gap-y-1 border-t border-stage-line px-4 py-2.5 text-[11.5px] text-stage-muted">
        <span className="flex items-center gap-1.5">
          <span className={cn("size-1.5 rounded-full", emo.bgClass)} /> {emo.label} · <span className="timecode">{intensity}%</span>
        </span>
        <span className="timecode">{s.engineMode ? `RX ${s.stats.framesReceived}` : "Engine off"}</span>
        <span className="ml-auto hidden sm:block">Preview is the engine's output only — nothing is animated in the browser.</span>
      </div>
    </div>
  );
}

function StageOverlay({ s, hasPortrait }: { s: StudioSession; hasPortrait: boolean }) {
  const st = s.stage;
  const box = (icon: ReactNode, title: string, body: ReactNode, action?: ReactNode, tone: "calm" | "alert" = "calm") => (
    <div className="absolute inset-x-4 bottom-12 flex justify-center sm:inset-x-8">
      <div className={cn("max-w-sm rounded-lg border bg-stage/85 p-4 text-center backdrop-blur-md animate-rise", tone === "alert" ? "border-live/40" : "border-stage-line")}>
        <div className="flex justify-center">{icon}</div>
        <p className="mt-2 text-sm font-semibold text-stage-foreground">{title}</p>
        <div className="mt-1 text-xs leading-relaxed text-stage-muted">{body}</div>
        {action && <div className="mt-3 flex justify-center gap-2">{action}</div>}
      </div>
    </div>
  );

  switch (st) {
    case "empty":
      return box(null, "Give your portrait a voice.", "Upload a portrait to create your avatar. It will appear here at 512×512.");
    case "preparing":
      return box(<Loader2 className="size-5 animate-spin text-stage-foreground" />, "Preparing portrait", "Reading the image and checking it for a face.");
    case "ready":
      return hasPortrait
        ? box(null, "Start speaking to preview the animation.", s.canStart.ok ? "Press Start session, then talk. Your voice drives the movement; your selected emotion shapes the expression." : s.canStart.reason)
        : null;
    case "initializing":
      return box(<Loader2 className="size-5 animate-spin text-stage-foreground" />, "Initialising engine", "Sending your portrait and building its appearance representation.");
    case "waiting":
      return box(<span className="size-2 rounded-full bg-live animate-rec" />, "Waiting for audio", "Connected. The first frames arrive once the engine hears your voice.");
    case "preview":
      return box(
        <Unplug className="size-5 text-stage-foreground" />,
        "Engine not connected",
        "Your microphone is live and the timeline is recording, but no frames are being rendered. Connect an EmoStream engine in Settings to see the animation.",
      );
    case "paused":
      return box(null, "Paused", "Audio isn't being sent. Resume when you're ready.");
    case "lost":
      return box(
        <WifiOff className="size-5 text-live" />,
        "Connection lost",
        "The engine stopped responding. Your portrait and settings are kept.",
        <>
          <Button size="sm" variant="stage" onClick={s.reset}>
            <RefreshCw /> Reset
          </Button>
          <Button size="sm" variant="live" onClick={() => { s.reset(); window.setTimeout(s.start, 50); }}>
            Reconnect
          </Button>
        </>,
        "alert",
      );
    case "complete":
      return box(
        <CheckCircle2 className="size-5 text-success" />,
        "Session complete",
        s.engineMode ? `${s.stats.framesReceived} frames received. Export the take or start a new one.` : "Timeline captured. No frames were rendered because no engine was connected.",
      );
    case "error":
      return box(
        <AlertTriangle className="size-5 text-live" />,
        "Something stopped the session",
        s.errorMsg ?? "The engine returned an error.",
        <Button size="sm" variant="stage" onClick={s.reset}>
          <RefreshCw /> Try again
        </Button>,
        "alert",
      );
    default:
      return null;
  }
}

function StateChip({ state }: { state: string }) {
  const map: Record<string, { label: string; cls: string; pulse?: boolean }> = {
    empty: { label: "No portrait", cls: "bg-stage-muted" },
    preparing: { label: "Preparing", cls: "bg-warning", pulse: true },
    ready: { label: "Ready", cls: "bg-success" },
    initializing: { label: "Initialising", cls: "bg-warning", pulse: true },
    waiting: { label: "Waiting for audio", cls: "bg-warning", pulse: true },
    active: { label: "Live", cls: "bg-live", pulse: true },
    preview: { label: "Mic live · no render", cls: "bg-live", pulse: true },
    paused: { label: "Paused", cls: "bg-warning" },
    lost: { label: "Connection lost", cls: "bg-live" },
    complete: { label: "Complete", cls: "bg-success" },
    error: { label: "Error", cls: "bg-live" },
  };
  const m = map[state] ?? { label: "No portrait", cls: "bg-stage-muted" };
  return (
    <span className="eyebrow flex items-center gap-2 text-[10px] text-stage-foreground">
      <span className={cn("size-1.5 rounded-full", m.cls, m.pulse && "animate-rec")} />
      {m.label}
    </span>
  );
}
