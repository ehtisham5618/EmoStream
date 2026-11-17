import { ChevronDown, FileDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useMemo, useState } from "react";
import { emotionById } from "@/lib/emotions";
import { duration, timecode } from "@/lib/format";
import { useSettings } from "@/lib/settings";
import { cn } from "@/lib/utils";
import type { StudioSession } from "./useStudioSession";

const BAR_COUNT = 220;

export function Timeline({ s }: { s: StudioSession }) {
  const defaultOpen = useSettings((x) => x.showTelemetry);
  const [open, setOpen] = useState<boolean | null>(null);
  const telemetryOpen = open ?? defaultOpen;
  const elapsed = s.mic.elapsed;
  const windowMs = Math.max(30000, Math.ceil((elapsed + 4000) / 10000) * 10000);
  const log = s.mic.log;

  const bars = useMemo(() => {
    const totalSlots = Math.round(windowMs / 50);
    const per = totalSlots / BAR_COUNT;
    return Array.from({ length: BAR_COUNT }, (_, i) => {
      const a = Math.floor(i * per);
      const b = Math.floor((i + 1) * per);
      let m = 0;
      for (let k = a; k < b && k < log.length; k++) m = Math.max(m, log[k] ?? 0);
      return { v: m, filled: a < log.length };
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [log.length, windowMs, s.mic.history]);

  const ticks = useMemo(() => {
    const step = windowMs <= 30000 ? 5000 : windowMs <= 60000 ? 10000 : 30000;
    return Array.from({ length: Math.floor(windowMs / step) + 1 }, (_, i) => i * step);
  }, [windowMs]);

  const progress = Math.min(1, elapsed / windowMs);
  const segments = s.events.map((e, i) => {
    const end = s.events[i + 1]?.t ?? elapsed;
    return { ...e, end };
  });

  return (
    <section className="panel overflow-hidden" aria-label="Timeline">
      <header className="flex flex-wrap items-center gap-x-6 gap-y-2 border-b border-border px-4 py-3">
        <h2 className="flex items-baseline gap-2">
          <span className="timecode text-[11px] text-ember">04</span>
          <span className="text-[13.5px] font-semibold">Timeline</span>
        </h2>
        <span className="timecode text-[1.05rem] font-medium">{timecode(elapsed)}</span>
        <span className="text-xs text-muted-foreground">
          Duration {duration(elapsed)} ·{" "}
          {s.events.length > 1
            ? `${s.events.length - 1} emotion change${s.events.length > 2 ? "s" : ""}`
            : "no emotion changes"}
        </span>
        <span className="ml-auto text-xs text-muted-foreground">{processingLabel(s)}</span>
      </header>

      <div className="relative px-4 pb-4 pt-2">
        {/* ruler */}
        <div className="relative ml-20 h-5">
          {ticks.map((t) => (
            <span
              key={t}
              className="timecode absolute top-0 -translate-x-1/2 text-[9.5px] text-muted-foreground"
              style={{ left: `${(t / windowMs) * 100}%` }}
            >
              {duration(t)}
            </span>
          ))}
        </div>

        <div className="relative space-y-1.5">
          <Track label="Voice">
            <svg
              viewBox={`0 0 ${BAR_COUNT * 3} 40`}
              preserveAspectRatio="none"
              className="h-full w-full"
              aria-hidden
            >
              {bars.map((b, i) => {
                const h = b.filled ? Math.max(1.5, b.v * 36) : 1;
                return (
                  <rect
                    key={i}
                    x={i * 3 + 0.5}
                    y={20 - h / 2}
                    width={2}
                    height={h}
                    rx={1}
                    className={b.filled ? "fill-foreground/75" : "fill-foreground/12"}
                  />
                );
              })}
            </svg>
          </Track>
          <Track label="Emotion">
            {segments.length === 0 ? (
              <span className="flex h-full items-center px-2 text-[11px] text-muted-foreground">
                Emotion changes appear here during a session.
              </span>
            ) : (
              segments.map((seg, i) => {
                const e = emotionById(seg.emotion);
                return (
                  <div
                    key={i}
                    className={cn(
                      "absolute inset-y-1 flex items-center overflow-hidden rounded-[3px] border-l-2 px-1.5",
                      e.borderClass,
                    )}
                    style={{
                      left: `${(seg.t / windowMs) * 100}%`,
                      width: `${Math.max(0.4, ((seg.end - seg.t) / windowMs) * 100)}%`,
                    }}
                    title={`${e.label} ${seg.intensity}% at ${duration(seg.t)}`}
                  >
                    <span className={cn("absolute inset-0 opacity-20", e.bgClass)} />
                    <span className="relative truncate text-[10.5px] font-medium">
                      {e.label}{" "}
                      <span className="timecode text-muted-foreground">{seg.intensity}</span>
                    </span>
                  </div>
                );
              })
            )}
          </Track>
          <Track label="Frames">
            {s.engineMode && s.frameLog.length > 0 ? (
              s.frameLog.map((n, i) => (
                <span
                  key={i}
                  className={cn(
                    "absolute inset-y-2 w-[2px] rounded-full",
                    n >= 20 ? "bg-success" : n > 0 ? "bg-warning" : "bg-live",
                  )}
                  style={{ left: `${((i * 1000 + 500) / windowMs) * 100}%` }}
                  title={`${n} frames in second ${i + 1}`}
                />
              ))
            ) : (
              <span className="flex h-full items-center px-2 text-[11px] text-muted-foreground">
                {s.engineMode
                  ? "Frame delivery appears once the engine starts sending."
                  : "No engine — no frames to show."}
              </span>
            )}
          </Track>
          {/* playhead */}
          <div className="pointer-events-none absolute inset-y-0 left-20 right-0">
            <div
              className="absolute -top-1 bottom-0 w-px bg-ember transition-[left] duration-100"
              style={{ left: `${progress * 100}%` }}
            >
              <span className="absolute -left-[3px] -top-1 size-[7px] rotate-45 bg-ember" />
            </div>
          </div>
        </div>
      </div>

      <div className="border-t border-border">
        <button
          onClick={() => setOpen(!telemetryOpen)}
          aria-expanded={telemetryOpen}
          className="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-accent/40"
        >
          <span className="eyebrow text-[10px] text-muted-foreground">Technical telemetry</span>
          <span
            className={cn(
              "rounded-full px-2 py-px font-mono text-[9.5px] uppercase tracking-wider",
              s.engineMode ? "bg-success/12 text-success" : "bg-muted text-muted-foreground",
            )}
          >
            {s.engineMode ? "Measured this session" : "Nothing measured yet"}
          </span>
          <ChevronDown
            className={cn(
              "ml-auto size-4 text-muted-foreground transition-transform duration-200",
              telemetryOpen && "rotate-180",
            )}
          />
        </button>
        <div
          className={cn(
            "grid transition-[grid-template-rows] duration-300 ease-soft",
            telemetryOpen ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
          )}
        >
          <div className="min-h-0 overflow-hidden">
            <dl className="grid grid-cols-2 gap-px border-t border-border bg-border sm:grid-cols-4 xl:grid-cols-8">
              <Metric k="FPS" v={fmt(s.stats.fps, 1)} />
              <Metric k="Server latency" v={fmt(s.stats.serverLatencyMs, 0, "ms")} />
              <Metric k="Client RTT" v={fmt(s.stats.clientRttMs, 0, "ms")} />
              <Metric k="Peak VRAM" v={fmt(s.stats.peakVramGiB, 2, "GiB")} />
              <Metric k="Frames received" v={s.engineMode ? String(s.stats.framesReceived) : "—"} />
              <Metric
                k="Frames displayed"
                v={s.engineMode ? String(s.stats.framesDisplayed) : "—"}
              />
              <Metric k="Dropped" v={s.engineMode ? String(s.stats.framesDropped) : "—"} />
              <Metric k="Connection" v={connLabel(s)} />
            </dl>
            <dl className="grid grid-cols-2 gap-px border-t border-border bg-border sm:grid-cols-4 xl:grid-cols-8">
              <Metric
                k="Voice ↔ lips"
                v={
                  s.diag.voiceOffsetP50Ms === null
                    ? "—"
                    : `${Math.round(s.diag.voiceOffsetP50Ms)} ms`
                }
              />
              <Metric
                k="Within 80 ms"
                v={
                  s.diag.voiceWithin80 === null
                    ? "—"
                    : `${Math.round(s.diag.voiceWithin80 * 100)} %`
                }
              />
              <Metric k="Avatar delay" v={fmt(s.diag.playoutDelayMs ?? undefined, 0, "ms")} />
              <Metric k="Server p95" v={fmt(s.diag.serverP95Ms ?? undefined, 0, "ms")} />
              <Metric
                k="Video"
                v={
                  s.diag.bitrateKbps === null || !s.engineMode
                    ? "—"
                    : `${s.diag.bitrateKbps} kb/s ${s.diag.codec === "h264" ? "H.264" : (s.diag.codec ?? "").toUpperCase()}`
                }
              />
              <Metric
                k="Startup"
                v={
                  s.diag.startupFirstFrameMs !== null
                    ? `${(s.diag.startupFirstFrameMs / 1000).toFixed(1)} s`
                    : s.diag.startupReadyMs !== null
                      ? `ready ${(s.diag.startupReadyMs / 1000).toFixed(1)} s`
                      : "—"
                }
              />
              <Metric
                k="Skipped srv / net"
                v={s.engineMode ? `${s.diag.serverSkipped} / ${s.diag.networkSkipped}` : "—"}
              />
              <Metric k="Uplink lag p95" v={fmt(s.diag.uplinkLagP95Ms ?? undefined, 0, "ms")} />
            </dl>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border px-4 py-2.5">
              <p className="min-w-0 flex-1 text-[11.5px] leading-snug text-muted-foreground">
                FPS counts pictures drawn on this screen. Server latency is the engine's own
                audio-to-frame time; the avatar delay adds network and buffering.{" "}
                {s.diag.gpu ? `Engine GPU: ${s.diag.gpu}.` : ""}
                {s.errorMsg ? ` Last error: ${s.errorMsg}` : ""}
              </p>
              <Button
                variant="hairline"
                size="sm"
                onClick={s.saveDiagnostics}
                disabled={!s.engineMode}
              >
                <FileDown /> Save diagnostics file
              </Button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function Track({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-stretch gap-0">
      <span className="eyebrow flex w-20 shrink-0 items-center text-[9.5px] text-muted-foreground">
        {label}
      </span>
      <div className="relative h-9 flex-1 overflow-hidden rounded-[4px] border border-border bg-sunk">
        {children}
      </div>
    </div>
  );
}

function Metric({ k, v }: { k: string; v: string }) {
  return (
    <div className="bg-surface px-3 py-2.5">
      <dt className="eyebrow text-[9px] text-muted-foreground">{k}</dt>
      <dd
        className={cn(
          "numeral mt-1 text-[1.05rem] font-medium",
          v === "—" && "text-muted-foreground/60",
        )}
        title={v === "—" ? "Not measured" : undefined}
      >
        {v}
      </dd>
    </div>
  );
}

const fmt = (n: number | undefined, d: number, unit = "") =>
  n === undefined ? "—" : `${n.toFixed(d)}${unit ? ` ${unit}` : ""}`;

function connLabel(s: StudioSession) {
  if (!s.engineMode) return "Idle";
  return {
    idle: "Idle",
    connecting: "Connecting",
    open: "Open",
    lost: "Lost",
    closed: "Closed",
    error: "Error",
  }[s.conn];
}

function processingLabel(s: StudioSession) {
  switch (s.stage) {
    case "active":
      return "Rendering on engine";
    case "initializing":
      return "Initialising";
    case "waiting":
      return "Waiting for audio";
    case "paused":
      return "Paused";
    case "complete":
      return "Session complete";
    case "lost":
      return "Connection lost";
    case "error":
      return "Stopped by error";
    default:
      return "Idle";
  }
}
