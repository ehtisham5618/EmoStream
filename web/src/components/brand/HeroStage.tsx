import { useEffect, useRef, useState } from "react";
import { faceFor, type EmotionId, emotionById } from "@/lib/emotions";
import { seededBars, speechEnvelope } from "@/lib/face-geometry";
import { timecode } from "@/lib/format";
import { cn } from "@/lib/utils";
import { FaceMesh } from "./FaceMesh";

const BARS = seededBars(120, 11);
const LOOP_MS = 9600;

/**
 * Editorial illustration of the EmoStream mechanism: speech envelope → jaw and lip motion,
 * emotion layer on top. Drawn landmarks, not a rendered portrait.
 */
export function HeroStage({ className }: { className?: string }) {
  const [t, setT] = useState(2400);
  const raf = useRef(0);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const t0 = performance.now();
    const tick = (now: number) => {
      setT((now - t0 + 2400) % LOOP_MS);
      raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, []);

  const progress = t / LOOP_MS;
  const emotion: EmotionId = progress < 0.5 ? "neutral" : "happy";
  const mouth = speechEnvelope(t / 1000) * 0.8;
  const params = faceFor(emotion, emotion === "happy" ? 70 : 0, { mouthOpen: mouth });
  const emo = emotionById(emotion);

  return (
    <figure className={cn("stage grain relative overflow-hidden rounded-xl", className)}>
      <div className="hairline-grid absolute inset-0 opacity-40" aria-hidden />
      {/* top bar */}
      <div className="relative z-[2] flex items-center justify-between border-b border-stage-line px-4 py-2.5">
        <span className="eyebrow flex items-center gap-2 text-stage-muted">
          <span className="size-1.5 rounded-full bg-live animate-rec" /> Preview · 512×512
        </span>
        <span className="timecode text-[11px] text-stage-foreground/80">{timecode(t)}</span>
      </div>

      <div className="relative z-[2] grid grid-cols-[1fr_auto] gap-0">
        <div className="relative aspect-square">
          {/* crop guides */}
          <CropGuides />
          <FaceMesh
            params={params}
            className="absolute inset-[3%] h-[94%] w-[94%] text-stage-foreground/85"
            lineClass="stroke-stage-foreground/80"
            dotClass="fill-stage-foreground/70"
          />
          <span className="eyebrow absolute bottom-3 left-4 text-stage-muted">
            Landmark illustration
          </span>
        </div>
        {/* parameter rail */}
        <div className="hidden w-36 flex-col justify-between border-l border-stage-line p-3 sm:flex">
          <Readout label="Jaw" value={mouth} />
          <Readout label="Lip aperture" value={mouth * 0.9} />
          <Readout label="Brow" value={params.browRaise * 0.5 + 0.5} />
          <div>
            <p className="eyebrow text-[9px] text-stage-muted">Emotion</p>
            <p
              className={cn(
                "mt-1 text-sm font-medium transition-colors duration-500",
                emo.colorClass,
              )}
            >
              {emo.label}
            </p>
            <p className="timecode text-[10px] text-stage-muted">
              {emotion === "happy" ? "70%" : "—"}
            </p>
          </div>
        </div>
      </div>

      {/* timeline */}
      <div className="relative z-[2] border-t border-stage-line px-4 pb-4 pt-3">
        <div className="mb-1.5 flex justify-between">
          <span className="eyebrow text-[9px] text-stage-muted">Voice</span>
          <span className="eyebrow text-[9px] text-stage-muted">Expression</span>
        </div>
        <div className="relative">
          <svg
            viewBox={`0 0 ${BARS.length * 4} 32`}
            preserveAspectRatio="none"
            className="h-8 w-full"
            aria-hidden
          >
            {BARS.map((v, i) => {
              const h = Math.round(Math.max(1.5, v * 30) * 100) / 100;
              const played = i / BARS.length <= progress;
              return (
                <rect
                  key={i}
                  x={i * 4 + 0.75}
                  y={16 - h / 2}
                  width={2.5}
                  height={h}
                  rx={1.2}
                  className={played ? "fill-stage-foreground/85" : "fill-stage-foreground/20"}
                />
              );
            })}
          </svg>
          <div className="mt-2 flex h-1.5 overflow-hidden rounded-full">
            <div className="w-1/2 bg-emo-neutral/60" />
            <div className="w-1/2 bg-emo-happy/80" />
          </div>
          <div
            className="pointer-events-none absolute -top-1 bottom-0 w-px bg-ember"
            style={{ left: `${progress * 100}%` }}
          />
        </div>
      </div>
    </figure>
  );
}

function Readout({ label, value }: { label: string; value: number }) {
  const v = Math.max(0, Math.min(1, value));
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <p className="eyebrow text-[9px] text-stage-muted">{label}</p>
        <p className="timecode text-[10px] text-stage-foreground/80">{v.toFixed(2)}</p>
      </div>
      <div className="mt-1 h-[3px] rounded-full bg-stage-line">
        <div
          className="h-full rounded-full bg-stage-foreground/70"
          style={{ width: `${v * 100}%` }}
        />
      </div>
    </div>
  );
}

export function CropGuides({ className }: { className?: string }) {
  const c = "absolute size-5 border-stage-foreground/45";
  return (
    <div className={cn("pointer-events-none absolute inset-4", className)} aria-hidden>
      <span className={cn(c, "left-0 top-0 border-l border-t")} />
      <span className={cn(c, "right-0 top-0 border-r border-t")} />
      <span className={cn(c, "bottom-0 left-0 border-b border-l")} />
      <span className={cn(c, "bottom-0 right-0 border-b border-r")} />
      <span className="absolute left-1/2 top-1/2 h-3 w-px -translate-x-1/2 -translate-y-1/2 bg-stage-foreground/30" />
      <span className="absolute left-1/2 top-1/2 h-px w-3 -translate-x-1/2 -translate-y-1/2 bg-stage-foreground/30" />
    </div>
  );
}
