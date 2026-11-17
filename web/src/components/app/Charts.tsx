import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** Chart frame with an explicit provenance label: measured, illustrative or live. */
export function ChartCard({
  label,
  title,
  provenance,
  children,
  foot,
  className,
}: {
  label: string;
  title: string;
  provenance: "measured" | "illustrative" | "demo" | "live";
  children: ReactNode;
  foot?: ReactNode;
  className?: string;
}) {
  const p = {
    measured: { t: "Measured", c: "border-success/30 bg-success/10 text-success" },
    illustrative: { t: "Illustrative", c: "border-ember/35 bg-ember/8 text-ember" },
    demo: { t: "Demonstration data", c: "border-ember/35 bg-ember/8 text-ember" },
    live: { t: "Live telemetry", c: "border-live/30 bg-live/10 text-live" },
  }[provenance];
  return (
    <figure className={cn("panel flex flex-col p-5", className)}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="eyebrow text-[10px] text-muted-foreground">{label}</p>
          <h3 className="mt-1 font-semibold">{title}</h3>
        </div>
        <span className={cn("shrink-0 rounded-full border px-2 py-[2px] font-mono text-[9.5px] uppercase tracking-wider", p.c)}>{p.t}</span>
      </div>
      <div className="mt-4 flex-1">{children}</div>
      {foot && <figcaption className="mt-3 text-[11.5px] leading-relaxed text-muted-foreground">{foot}</figcaption>}
    </figure>
  );
}

export const axis = { stroke: "var(--muted-foreground)", fontSize: 10, fontFamily: "var(--font-mono)", tickLine: false, axisLine: false } as const;
export const grid = { stroke: "var(--border)", strokeDasharray: "2 4", vertical: false } as const;
export const tooltipStyle = {
  contentStyle: { background: "var(--popover)", border: "1px solid var(--border)", borderRadius: 6, fontSize: 12, color: "var(--popover-foreground)" },
  labelStyle: { color: "var(--muted-foreground)", fontFamily: "var(--font-mono)", fontSize: 10 },
  cursor: { fill: "var(--accent)", opacity: 0.4 },
} as const;
