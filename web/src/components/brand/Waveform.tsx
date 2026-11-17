import { useMemo } from "react";
import { seededBars } from "@/lib/face-geometry";
import { cn } from "@/lib/utils";

/** Static, deterministic waveform motif. Use for illustration only. */
export function WaveformMotif({
  bars = 96,
  seed = 7,
  className,
  barClass = "fill-current",
  highlightUntil,
  highlightClass = "fill-ember",
}: {
  bars?: number;
  seed?: number;
  className?: string;
  barClass?: string;
  highlightUntil?: number;
  highlightClass?: string;
}) {
  const values = useMemo(() => seededBars(bars, seed), [bars, seed]);
  const w = bars * 4;
  return (
    <svg viewBox={`0 0 ${w} 40`} preserveAspectRatio="none" className={cn("block", className)} aria-hidden="true">
      {values.map((v, i) => {
        const h = Math.round(Math.max(1.5, v * 38) * 100) / 100;
        return (
          <rect
            key={i}
            x={i * 4 + 0.75}
            y={20 - h / 2}
            width={2.5}
            height={h}
            rx={1.25}
            className={highlightUntil !== undefined && i / bars <= highlightUntil ? highlightClass : barClass}
          />
        );
      })}
    </svg>
  );
}

/** Live waveform from an array of 0–1 levels (newest last). */
export function LiveBars({ levels, className, barClass = "fill-current" }: { levels: number[]; className?: string; barClass?: string }) {
  const n = levels.length || 1;
  return (
    <svg viewBox={`0 0 ${n * 4} 40`} preserveAspectRatio="none" className={cn("block", className)} aria-hidden="true">
      {levels.map((v, i) => {
        const h = Math.round(Math.max(1.2, Math.min(1, v) * 38) * 100) / 100;
        return <rect key={i} x={i * 4 + 0.75} y={20 - h / 2} width={2.5} height={h} rx={1.25} className={barClass} />;
      })}
    </svg>
  );
}
