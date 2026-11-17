import { createFileRoute, Link } from "@tanstack/react-router";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Page, PageHeader } from "@/components/app/PageHeader";
import { ChartCard, axis, grid, tooltipStyle } from "@/components/app/Charts";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { DISCLAIMER, HARDWARE, LATENCY_NOTE, VALIDATION } from "@/lib/benchmarks";
import {
  EMOTION_ORDER,
  ILLUSTRATIVE_CONFUSION,
  ILLUSTRATIVE_DELIVERY,
  ILLUSTRATIVE_FPS,
  ILLUSTRATIVE_INTENSITY,
  ILLUSTRATIVE_LATENCY,
  macroF1,
} from "@/lib/demo-data";
import { emotionById } from "@/lib/emotions";
import { duration } from "@/lib/format";
import { useStudio } from "@/lib/studio-store";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/app/analytics")({
  head: () => ({
    meta: [
      { title: "Analytics — EmoStream" },
      { name: "description", content: "Performance and animation-quality results for EmoStream, with recorded experiments kept separate from live telemetry." },
      { property: "og:title", content: "Analytics — EmoStream" },
      { property: "og:description", content: "EmoStream performance and animation-quality analytics." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: Analytics,
});

function Analytics() {
  return (
    <Page wide>
      <PageHeader
        label="Insights · Analytics"
        title="Performance and animation quality"
        description="Recorded experiments and live telemetry are kept apart. Measured values come from the validation report; charts marked Illustrative are shaped around those values to show how results will be read, and are not raw data."
      />
      <Tabs defaultValue="recorded" className="mt-6">
        <TabsList className="h-auto bg-sunk p-1">
          <TabsTrigger value="recorded" className="px-4 py-1.5">Recorded experiments</TabsTrigger>
          <TabsTrigger value="live" className="px-4 py-1.5">Live telemetry</TabsTrigger>
        </TabsList>
        <TabsContent value="recorded" className="mt-6 space-y-6">
          <Recorded />
        </TabsContent>
        <TabsContent value="live" className="mt-6">
          <Live />
        </TabsContent>
      </Tabs>
    </Page>
  );
}

function MetricTile({ k, v, unit, note, missing }: { k: string; v?: string; unit?: string; note: string; missing?: boolean }) {
  return (
    <div className="bg-surface p-4">
      <dt className="eyebrow text-[9.5px] text-muted-foreground">{k}</dt>
      <dd className="mt-2 flex items-baseline gap-1">
        {missing ? (
          <span className="text-sm font-medium text-muted-foreground">Not reported</span>
        ) : (
          <>
            <span className="numeral text-[1.9rem] font-medium leading-none">{v}</span>
            {unit && <span className="text-xs text-muted-foreground">{unit}</span>}
          </>
        )}
      </dd>
      <p className="timecode mt-1.5 text-[10px] text-muted-foreground">{note}</p>
    </div>
  );
}

function Recorded() {
  const f1 = macroF1(ILLUSTRATIVE_CONFUSION);
  return (
    <>
      <div className="grid gap-6 xl:grid-cols-2">
        <section>
          <p className="eyebrow mb-2 text-muted-foreground">Performance</p>
          <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-border bg-border sm:grid-cols-3">
            <MetricTile k="FPS" v="≈25" note="L40S · TensorRT" />
            <MetricTile k="p50 latency" v={String(VALIDATION.serverP50Ms)} unit="ms" note="server-side" />
            <MetricTile k="p95 latency" v={String(VALIDATION.serverP95Ms)} unit="ms" note="server-side" />
            <MetricTile k="GPU memory" v={String(VALIDATION.peakVramGiB)} unit="GiB" note="peak, tested hw" />
            <MetricTile k="Frame delivery" missing note="awaiting report" />
            <MetricTile k="Session stability" missing note="awaiting report" />
          </dl>
        </section>
        <section>
          <p className="eyebrow mb-2 text-muted-foreground">Animation quality</p>
          <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-border bg-border sm:grid-cols-3">
            <MetricTile k="Emotion macro-F1" v={VALIDATION.emotionMacroF1.toFixed(3)} note="5 classes" />
            <MetricTile k="Identity similarity" v={VALIDATION.arcface.toFixed(3)} note="ArcFace cosine" />
            <MetricTile k="Lip synchronisation" missing note="awaiting report" />
            <MetricTile k="Motion smoothness" missing note="awaiting report" />
            <MetricTile k="Boundary jerk" missing note="awaiting report" />
            <div className="bg-sunk p-4 text-[11px] leading-relaxed text-muted-foreground">Metrics without a supplied figure stay empty rather than estimated.</div>
          </dl>
        </section>
      </div>
      <p className="border-l-2 border-ember pl-4 text-sm text-muted-foreground">{DISCLAIMER} {LATENCY_NOTE}</p>

      <div className="grid gap-5 lg:grid-cols-2">
        <ChartCard label="Performance over time" title="Frame rate across a 60 s run" provenance="illustrative" foot="Trace centred on the reported ≈25 FPS mean. Replace with the run log when published.">
          <div className="h-56">
            <ResponsiveContainer>
              <AreaChart data={ILLUSTRATIVE_FPS} margin={{ left: -20, right: 8, top: 8 }}>
                <defs>
                  <linearGradient id="fpsFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.25} />
                    <stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid {...grid} />
                <XAxis dataKey="t" {...axis} tickFormatter={(v) => `${v}s`} interval={9} />
                <YAxis {...axis} domain={[18, 28]} />
                <ReferenceLine y={25} stroke="var(--ember)" strokeDasharray="3 3" />
                <Tooltip {...tooltipStyle} formatter={(v: number) => [`${v} fps`, "FPS"]} labelFormatter={(l) => `t = ${l}s`} />
                <Area type="monotone" dataKey="fps" stroke="var(--chart-1)" strokeWidth={1.5} fill="url(#fpsFill)" isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </ChartCard>

        <ChartCard label="Latency distribution" title="Server-side latency per frame" provenance="illustrative" foot="Shape fitted to the reported p50 (269 ms) and p95 (319 ms). Server-side only — not what a viewer feels end to end.">
          <div className="h-56">
            <ResponsiveContainer>
              <BarChart data={ILLUSTRATIVE_LATENCY} margin={{ left: -20, right: 8, top: 18 }}>
                <CartesianGrid {...grid} />
                <XAxis dataKey="lo" {...axis} tickFormatter={(v) => `${v}`} />
                <YAxis {...axis} />
                <ReferenceLine x={260} stroke="var(--chart-1)" label={{ value: "p50", fill: "var(--muted-foreground)", fontSize: 10, position: "top" }} />
                <ReferenceLine x={310} stroke="var(--ember)" label={{ value: "p95", fill: "var(--muted-foreground)", fontSize: 10, position: "top" }} />
                <Tooltip {...tooltipStyle} formatter={(v: number) => [v, "frames"]} labelFormatter={(l) => `${l}–${Number(l) + 10} ms`} />
                <Bar dataKey="count" fill="var(--chart-3)" radius={[2, 2, 0, 0]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </ChartCard>

        <ChartCard
          label="Emotion recognition"
          title="Confusion matrix (row-normalised)"
          provenance="illustrative"
          foot={`Constructed to match the reported macro-F1 (this matrix gives ${f1.toFixed(3)}). It is not the validation report's matrix.`}
        >
          <ConfusionMatrix />
        </ChartCard>

        <ChartCard label="Frame delivery" title="Frames delivered per second" provenance="illustrative" foot="Expected 25 per second. Drops shown in terracotta. Shape only; no delivery figures were supplied.">
          <div className="h-56">
            <ResponsiveContainer>
              <BarChart data={ILLUSTRATIVE_DELIVERY} margin={{ left: -20, right: 8, top: 8 }}>
                <CartesianGrid {...grid} />
                <XAxis dataKey="t" {...axis} interval={4} tickFormatter={(v) => `${v}s`} />
                <YAxis {...axis} domain={[0, 26]} />
                <Tooltip {...tooltipStyle} />
                <Bar dataKey="delivered" stackId="a" fill="var(--chart-1)" isAnimationActive={false} />
                <Bar dataKey="dropped" stackId="a" fill="var(--ember)" isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </ChartCard>

        <ChartCard label="Emotion intensity" title="Intensity chosen across sessions" provenance="demo" foot="From the demonstration session records, not from real users.">
          <div className="h-48">
            <ResponsiveContainer>
              <BarChart data={ILLUSTRATIVE_INTENSITY} margin={{ left: -20, right: 8, top: 8 }}>
                <CartesianGrid {...grid} />
                <XAxis dataKey="band" {...axis} />
                <YAxis {...axis} allowDecimals={false} />
                <Tooltip {...tooltipStyle} />
                <Bar dataKey="count" fill="var(--chart-4)" radius={[2, 2, 0, 0]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </ChartCard>

        <ChartCard label="Model comparison" title="Hardware coverage" provenance="measured" foot="Only the L40S has published figures. No GPU is claimed to reach 25 FPS unless it was measured.">
          <ul className="divide-y divide-border text-sm">
            {HARDWARE.map((h) => (
              <li key={h.gpu} className="grid grid-cols-[1fr_auto] gap-2 py-3">
                <div>
                  <p className="font-medium">{h.gpu}</p>
                  <p className="text-xs text-muted-foreground">{h.note}</p>
                </div>
                <div className="text-right">
                  {h.fps ? (
                    <>
                      <p className="numeral text-lg font-medium">{h.fps} fps</p>
                      <p className="timecode text-[10px] text-muted-foreground">p50 {h.p50} · {h.vram}</p>
                    </>
                  ) : (
                    <span className={cn("font-mono text-[10px] uppercase tracking-wider", h.status === "tested" ? "text-muted-foreground" : "text-soon")}>
                      {h.status === "tested" ? "Figures pending" : "Not yet verified"}
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </ChartCard>
      </div>
    </>
  );
}

function ConfusionMatrix() {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-separate border-spacing-[3px] text-center">
        <thead>
          <tr>
            <th className="w-20" />
            {EMOTION_ORDER.map((e) => (
              <th key={e} className="eyebrow pb-1 text-[9px] font-normal text-muted-foreground">{emotionById(e).label.slice(0, 4)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ILLUSTRATIVE_CONFUSION.map((row, i) => (
            <tr key={i}>
              <th className="eyebrow pr-2 text-right text-[9px] font-normal text-muted-foreground">{emotionById(EMOTION_ORDER[i] ?? "neutral").label}</th>
              {row.map((v, j) => (
                <td
                  key={j}
                  className={cn("timecode h-10 rounded-[3px] text-[11px]", i === j ? "text-primary-foreground" : "text-foreground")}
                  style={{ background: i === j ? `color-mix(in oklab, var(--primary) ${40 + v * 60}%, transparent)` : `color-mix(in oklab, var(--ember) ${v * 140}%, transparent)` }}
                >
                  {v.toFixed(2)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="timecode mt-2 text-[10px] text-muted-foreground">rows: true emotion · columns: predicted</p>
    </div>
  );
}

function Live() {
  const sessions = useStudio((s) => s.sessions);
  const rendered = sessions.filter((s) => s.engine);
  if (sessions.length === 0)
    return (
      <div className="rounded-xl border border-dashed border-input p-10 text-center">
        <p className="display-md">No live telemetry yet.</p>
        <p className="mx-auto mt-3 max-w-md text-muted-foreground">
          Live numbers come only from sessions you run with an engine connected. Nothing is estimated or filled in.
        </p>
        <Button asChild variant="ink" className="mt-6">
          <Link to="/app/studio">Run a session</Link>
        </Button>
      </div>
    );
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        {rendered.length} of {sessions.length} takes this visit were rendered by an engine. Detailed per-frame telemetry is shown in the Studio timeline while a session runs.
      </p>
      <div className="overflow-hidden rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead className="bg-sunk">
            <tr className="eyebrow text-left text-[10px] text-muted-foreground">
              <th className="px-4 py-3 font-medium">Take</th>
              <th className="px-3 py-3 font-medium">Duration</th>
              <th className="px-3 py-3 font-medium">Frames received</th>
              <th className="px-3 py-3 font-medium">Mean FPS</th>
              <th className="px-3 py-3 font-medium">Source</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border bg-surface">
            {sessions.map((s) => (
              <tr key={s.id}>
                <td className="px-4 py-3">{s.avatarName}</td>
                <td className="timecode px-3 py-3">{duration(s.durationMs)}</td>
                <td className="timecode px-3 py-3">{s.engine ? s.framesReceived : "—"}</td>
                <td className="timecode px-3 py-3">{s.engine && s.durationMs > 0 ? (s.framesReceived / (s.durationMs / 1000)).toFixed(1) : "—"}</td>
                <td className="px-3 py-3 text-muted-foreground">{s.engine ? "Engine" : "No engine · not measured"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
