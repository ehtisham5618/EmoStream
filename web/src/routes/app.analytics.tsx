import { createFileRoute, Link } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Page, PageHeader } from "@/components/app/PageHeader";
import { ChartCard, axis, grid, tooltipStyle } from "@/components/app/Charts";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { CURRENT, DISCLAIMER, HARDWARE, LATENCY_NOTE, MODEL_HISTORY, VALIDATION } from "@/lib/benchmarks";
import { duration } from "@/lib/format";
import { useStudio, type SessionSummary } from "@/lib/studio-store";
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
        description="Recorded experiments and live telemetry are kept apart. Every figure names the model, date and hardware it was measured on. Charts are drawn only from sessions you run in this tab; nothing is estimated or filled in."
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
          <span className="text-sm font-medium text-muted-foreground">Not measured</span>
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

/** Takes from this tab with per-second telemetry, newest first. */
function useMeasuredTakes() {
  return useStudio((s) => s.sessions).filter((s) => s.engine && s.framesReceived > 0);
}

function NoTake({ what }: { what: string }) {
  return (
    <div className="flex h-full min-h-40 flex-col items-center justify-center gap-3 rounded-md border border-dashed border-input p-6 text-center">
      <p className="text-sm text-muted-foreground">Run a Studio session to see {what} here. Nothing is plotted without a measurement.</p>
      <Button asChild variant="hairline" size="sm">
        <Link to="/app/studio">Open Studio</Link>
      </Button>
    </div>
  );
}

function latencyBins(values: number[]) {
  if (!values.length) return [];
  const sorted = [...values].sort((a, b) => a - b);
  const lo = Math.floor((sorted[Math.floor(sorted.length * 0.01)] ?? 0) / 20) * 20;
  const hi = Math.ceil((sorted[Math.floor(sorted.length * 0.99)] ?? 0) / 20) * 20 + 20;
  const bins: { lo: number; count: number }[] = [];
  for (let b = lo; b < hi; b += 20) bins.push({ lo: b, count: 0 });
  for (const v of values) {
    const k = Math.min(bins.length - 1, Math.max(0, Math.floor((v - lo) / 20)));
    bins[k]!.count++;
  }
  return bins;
}

const quantile = (values: number[], q: number) => {
  const s = [...values].sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.floor(q * s.length))] ?? 0;
};

function Recorded() {
  const takes = useMeasuredTakes();
  const latest: SessionSummary | undefined = takes[0];
  const fps = latest ? latest.fpsPerSecond.map((v, t) => ({ t, fps: v })) : [];
  const delivery = latest ? latest.deliveredPerSecond.map((d, t) => ({ t, delivered: d, dropped: latest.droppedPerSecond[t] ?? 0 })) : [];
  const lat = latest?.latencyMs ?? [];
  const bins = latencyBins(lat);
  const p50 = lat.length ? quantile(lat, 0.5) : null;
  const p95 = lat.length ? quantile(lat, 0.95) : null;
  const intensities = takes.flatMap((s) => s.intensities);
  const bands = [
    { band: "0–20", count: intensities.filter((v) => v <= 20).length },
    { band: "21–40", count: intensities.filter((v) => v > 20 && v <= 40).length },
    { band: "41–60", count: intensities.filter((v) => v > 40 && v <= 60).length },
    { band: "61–80", count: intensities.filter((v) => v > 60 && v <= 80).length },
    { band: "81–100", count: intensities.filter((v) => v > 80).length },
  ];
  const takeFoot = (rest: string) =>
    latest ? `Your latest take this visit (${latest.avatarName}, ${duration(latest.durationMs)}). ${rest}` : rest;

  return (
    <>
      <div className="grid gap-6 xl:grid-cols-2">
        <section>
          <p className="eyebrow mb-2 text-muted-foreground">Performance</p>
          <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-border bg-border sm:grid-cols-3">
            <MetricTile k="FPS" v="≈25" note={`L40S · TensorRT · ${VALIDATION.date}`} />
            <MetricTile k="p50 latency" v={String(VALIDATION.serverP50Ms)} unit="ms" note={`server-side · ${VALIDATION.date}`} />
            <MetricTile k="p95 latency" v={String(VALIDATION.serverP95Ms)} unit="ms" note={`server-side · ${VALIDATION.date}`} />
            <MetricTile k="GPU memory" v={String(VALIDATION.peakVramGiB)} unit="GiB" note={`peak · L40S · ${VALIDATION.date}`} />
            <MetricTile k="Frame delivery" v={`${CURRENT.liveFramesSkipped}/${CURRENT.liveFramesTotal}`} note={`skipped · live ${CURRENT.model} · browser test`} />
            <MetricTile k="Session stability" missing note="no long-run browser test yet" />
          </dl>
        </section>
        <section>
          <p className="eyebrow mb-2 text-muted-foreground">Animation quality · live model {CURRENT.model}</p>
          <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-border bg-border sm:grid-cols-3">
            <MetricTile k="Emotion macro-F1" v={CURRENT.emotionMacroF1.toFixed(3)} note="5 classes · MEAD val" />
            <MetricTile k="Identity similarity" v={CURRENT.arcface.toFixed(3)} note="ArcFace cosine" />
            <MetricTile k="Lip synchronisation" v={CURRENT.lseC.toFixed(2)} note={`SyncNet LSE-C · real ${CURRENT.realLseC}`} />
            <MetricTile k="Mouth opening" v={CURRENT.mouthOpenCorr.toFixed(3)} note="correlation with real" />
            <MetricTile k="/p b m/ closure" v={CURRENT.bilabialPrecision.toFixed(2)} note="strict precision" />
            <MetricTile k="Boundary jerk" missing note="not measured for this model" />
          </dl>
        </section>
      </div>
      <p className="border-l-2 border-ember pl-4 text-sm text-muted-foreground">
        {DISCLAIMER} {LATENCY_NOTE} Engine figures: model {VALIDATION.model}, {VALIDATION.date}. Quality figures: model {CURRENT.model}, 80 MEAD validation clips, {CURRENT.date}.
      </p>

      <div className="grid gap-5 lg:grid-cols-2">
        <ChartCard label="Performance over time" title="Pictures drawn per second" provenance={latest ? "live" : "measured"} foot={takeFoot("Counted in this browser: distinct frames shown on screen each second. The engine sends 25.")}>
          <div className="h-56">
            {fps.length ? (
              <ResponsiveContainer>
                <AreaChart data={fps} margin={{ left: -20, right: 8, top: 8 }}>
                  <defs>
                    <linearGradient id="fpsFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.25} />
                      <stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid {...grid} />
                  <XAxis dataKey="t" {...axis} tickFormatter={(v) => `${v}s`} interval="preserveStartEnd" />
                  <YAxis {...axis} domain={[0, 30]} />
                  <ReferenceLine y={25} stroke="var(--ember)" strokeDasharray="3 3" />
                  <Tooltip {...tooltipStyle} formatter={(v: number) => [`${v} fps`, "Drawn"]} labelFormatter={(l) => `t = ${l}s`} />
                  <Area type="monotone" dataKey="fps" stroke="var(--chart-1)" strokeWidth={1.5} fill="url(#fpsFill)" isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <NoTake what="its frame rate" />
            )}
          </div>
        </ChartCard>

        <ChartCard
          label="Latency distribution"
          title="Server-side latency per frame"
          provenance={latest ? "live" : "measured"}
          foot={takeFoot(p50 !== null ? `From each frame's header: p50 ${Math.round(p50)} ms, p95 ${Math.round(p95 ?? 0)} ms over ${lat.length} frames. Server-side only — not what a viewer feels end to end.` : "From each frame's header. Server-side only — not what a viewer feels end to end.")}
        >
          <div className="h-56">
            {bins.length ? (
              <ResponsiveContainer>
                <BarChart data={bins} margin={{ left: -20, right: 8, top: 18 }}>
                  <CartesianGrid {...grid} />
                  <XAxis dataKey="lo" {...axis} tickFormatter={(v) => `${v}`} />
                  <YAxis {...axis} allowDecimals={false} />
                  <Tooltip {...tooltipStyle} formatter={(v: number) => [v, "frames"]} labelFormatter={(l) => `${l}–${Number(l) + 20} ms`} />
                  <Bar dataKey="count" fill="var(--chart-3)" radius={[2, 2, 0, 0]} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <NoTake what="its latency distribution" />
            )}
          </div>
        </ChartCard>

        <ChartCard label="Model comparison" title="Validation history, same evaluation" provenance="measured" foot="80 MEAD validation clips rendered by the live engine; validation actors only. Empty cells were not measured for that model.">
          <ModelHistory />
        </ChartCard>

        <ChartCard label="Frame delivery" title="Frames received per second" provenance={latest ? "live" : "measured"} foot={takeFoot("Expected 25 per second while you speak. Lost frames (skipped by the engine or the network, or late here) shown in terracotta.")}>
          <div className="h-56">
            {delivery.length ? (
              <ResponsiveContainer>
                <BarChart data={delivery} margin={{ left: -20, right: 8, top: 8 }}>
                  <CartesianGrid {...grid} />
                  <XAxis dataKey="t" {...axis} interval="preserveStartEnd" tickFormatter={(v) => `${v}s`} />
                  <YAxis {...axis} domain={[0, 30]} />
                  <Tooltip {...tooltipStyle} />
                  <Bar dataKey="delivered" stackId="a" fill="var(--chart-1)" isAnimationActive={false} />
                  <Bar dataKey="dropped" stackId="a" fill="var(--ember)" isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <NoTake what="its frame delivery" />
            )}
          </div>
        </ChartCard>

        <ChartCard label="Emotion intensity" title="Intensity chosen across your takes" provenance={takes.length ? "live" : "measured"} foot="Every emotion setting used in takes from this tab.">
          <div className="h-48">
            {intensities.length ? (
              <ResponsiveContainer>
                <BarChart data={bands} margin={{ left: -20, right: 8, top: 8 }}>
                  <CartesianGrid {...grid} />
                  <XAxis dataKey="band" {...axis} />
                  <YAxis {...axis} allowDecimals={false} />
                  <Tooltip {...tooltipStyle} />
                  <Bar dataKey="count" fill="var(--chart-4)" radius={[2, 2, 0, 0]} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <NoTake what="the intensities you used" />
            )}
          </div>
        </ChartCard>

        <ChartCard label="Hardware" title="Hardware coverage" provenance="measured" foot={`Only the L40S has engine figures (${VALIDATION.date} run). No GPU is claimed to reach 25 FPS unless it was measured.`}>
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
                      {h.status === "tested" ? "No live figures" : "Not yet verified"}
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

function ModelHistory() {
  const cell = (v: ReactNode) => <td className="timecode px-2 py-2.5 text-right">{v ?? <span className="text-muted-foreground/60">—</span>}</td>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="eyebrow text-left text-[9px] text-muted-foreground">
            <th className="py-2 pr-2 font-normal">Model</th>
            <th className="px-2 py-2 text-right font-normal">LSE-C / D</th>
            <th className="px-2 py-2 text-right font-normal">Mouth corr</th>
            <th className="px-2 py-2 text-right font-normal">Emo F1</th>
            <th className="px-2 py-2 text-right font-normal">ArcFace</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {MODEL_HISTORY.map((m) => (
            <tr key={m.model}>
              <td className="py-2.5 pr-2">
                <p className={cn("font-medium", m.model === CURRENT.model && "text-ember")}>{m.model}</p>
                <p className="text-[11px] text-muted-foreground">{m.note}</p>
              </td>
              {cell(m.lseC !== undefined && m.lseD !== undefined ? `${m.lseC.toFixed(2)} / ${m.lseD.toFixed(2)}` : null)}
              {cell(m.mouthCorr.toFixed(3))}
              {cell(m.f1 !== undefined ? m.f1.toFixed(2) : null)}
              {cell(m.arcface !== undefined ? m.arcface.toFixed(3) : null)}
            </tr>
          ))}
          <tr>
            <td className="py-2.5 pr-2">
              <p className="font-medium">Real video</p>
              <p className="text-[11px] text-muted-foreground">MEAD recordings, reference</p>
            </td>
            {cell(`${CURRENT.realLseC.toFixed(2)} / ${CURRENT.realLseD.toFixed(2)}`)}
            {cell("1.000")}
            {cell("0.73")}
            {cell("0.754")}
          </tr>
        </tbody>
      </table>
      <p className="timecode mt-2 text-[10px] text-muted-foreground">higher LSE-C, lower LSE-D = better lip sync · reg mouth corr from block streaming</p>
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
          Live numbers come only from sessions you run in the Studio. Nothing is estimated or filled in.
        </p>
        <Button asChild variant="ink" className="mt-6">
          <Link to="/app/studio">Run a session</Link>
        </Button>
      </div>
    );
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        {rendered.length} of {sessions.length} takes this visit were rendered by the engine. Detailed per-frame telemetry is shown in the Studio timeline while a session runs, and can be saved from there as a diagnostics file.
      </p>
      <div className="overflow-hidden rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead className="bg-sunk">
            <tr className="eyebrow text-left text-[10px] text-muted-foreground">
              <th className="px-4 py-3 font-medium">Take</th>
              <th className="px-3 py-3 font-medium">Duration</th>
              <th className="px-3 py-3 font-medium">Frames received</th>
              <th className="px-3 py-3 font-medium">Drawn FPS (median)</th>
              <th className="px-3 py-3 font-medium">Server p50</th>
              <th className="px-3 py-3 font-medium">Ended</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border bg-surface">
            {sessions.map((s) => (
              <tr key={s.id}>
                <td className="px-4 py-3">{s.avatarName}</td>
                <td className="timecode px-3 py-3">{duration(s.durationMs)}</td>
                <td className="timecode px-3 py-3">{s.framesReceived}</td>
                <td className="timecode px-3 py-3">{s.fpsPerSecond.length ? quantile(s.fpsPerSecond, 0.5).toFixed(1) : "—"}</td>
                <td className="timecode px-3 py-3">{s.latencyMs.length ? `${Math.round(quantile(s.latencyMs, 0.5))} ms` : "—"}</td>
                <td className="px-3 py-3 text-muted-foreground">{s.outcome === "complete" ? "Completed" : s.outcome === "lost" ? "Connection lost" : "Error"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
