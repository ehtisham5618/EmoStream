import { createFileRoute, Link } from "@tanstack/react-router";
import { RefreshCw } from "lucide-react";
import { Page, PageHeader, SectionTitle } from "@/components/app/PageHeader";
import { StatusPill } from "@/components/app/Status";
import { PipelineDiagram } from "@/components/brand/PipelineDiagram";
import { Button } from "@/components/ui/button";
import { DISCLAIMER, HARDWARE, LATENCY_NOTE, MODEL, VALIDATION } from "@/lib/benchmarks";
import { useEngineStatus } from "@/lib/engine/useEngineStatus";

export const Route = createFileRoute("/app/models")({
  head: () => ({
    meta: [
      { title: "Models & Performance — EmoStream" },
      { name: "description", content: "EmoStream's architecture, BehaviourNet model details, the LivePortrait renderer and validated benchmarks with their conditions." },
      { property: "og:title", content: "Models & Performance — EmoStream" },
      { property: "og:description", content: "Architecture, model details and validated benchmarks for EmoStream." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: Models,
});

function Models() {
  const { status, info, refetch, engineUrl } = useEngineStatus();
  return (
    <Page wide>
      <PageHeader label="Insights · Models & Performance" title="How EmoStream is built, and how fast it runs" description="One small trained model between two frozen ones. The numbers below come from validation runs with the conditions stated next to them." />

      <section className="mt-8">
        <SectionTitle label="Architecture" title="From portrait and voice to a video stream" />
        <PipelineDiagram />
      </section>

      <section className="mt-10 grid gap-5 lg:grid-cols-3">
        <div className="panel p-6 lg:col-span-1">
          <p className="eyebrow text-muted-foreground">Trained model</p>
          <h3 className="font-display mt-2 text-3xl">{MODEL.name}</h3>
          <p className="mt-4 flex items-baseline gap-1.5">
            <span className="numeral text-5xl font-medium">{MODEL.params}</span>
            <span className="text-sm text-muted-foreground">parameters</span>
          </p>
          <ul className="mt-5 space-y-2 text-sm">
            {MODEL.facts.map((f) => (
              <li key={f} className="flex gap-2.5"><span className="mt-2 h-px w-3 shrink-0 bg-ember" />{f}</li>
            ))}
          </ul>
        </div>
        <div className="panel p-6">
          <p className="eyebrow text-muted-foreground">Renderer</p>
          <h3 className="font-display mt-2 text-3xl">LivePortrait</h3>
          <p className="mt-3 text-sm text-muted-foreground">{MODEL.renderer}. EmoStream doesn't retrain it; BehaviourNet produces the motion it renders.</p>
          <p className="eyebrow mt-6 text-muted-foreground">Audio encoder</p>
          <h3 className="font-display mt-2 text-3xl">{MODEL.audioEncoder}</h3>
          <p className="mt-3 text-sm text-muted-foreground">Turns raw speech into features BehaviourNet can read frame by frame.</p>
        </div>
        <div className="panel flex flex-col p-6">
          <div className="flex items-center justify-between">
            <p className="eyebrow text-muted-foreground">Connected engine</p>
            <StatusPill tone={status === "online" ? "success" : status === "offline" ? "live" : "muted"} dot>{status === "unset" ? "none" : status}</StatusPill>
          </div>
          {status === "online" && info?.raw ? (
            <dl className="mt-4 max-h-56 divide-y divide-border overflow-auto text-xs">
              {Object.entries(info.raw).map(([k, v]) => (
                <div key={k} className="flex justify-between gap-4 py-2">
                  <dt className="timecode text-muted-foreground">{k}</dt>
                  <dd className="timecode truncate text-right">{typeof v === "object" ? JSON.stringify(v) : String(v)}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="mt-4 text-sm text-muted-foreground">
              {status === "unset" ? "Connect an engine to read its GPU, model and build details from /api/info." : info?.error ?? "Checking…"}
            </p>
          )}
          <div className="mt-auto flex gap-2 pt-5">
            {engineUrl ? (
              <Button variant="hairline" size="sm" onClick={() => refetch()}><RefreshCw /> Refresh</Button>
            ) : (
              <Button asChild variant="hairline" size="sm"><Link to="/app/settings" hash="performance">Add engine address</Link></Button>
            )}
          </div>
        </div>
      </section>

      <section className="mt-10">
        <SectionTitle label="Benchmarks" title="Validation results and their conditions" />
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full min-w-[720px] text-sm">
            <thead className="bg-sunk">
              <tr className="eyebrow text-left text-[10px] text-muted-foreground">
                <th className="px-4 py-3 font-medium">Hardware</th>
                <th className="px-3 py-3 font-medium">Status</th>
                <th className="px-3 py-3 font-medium">FPS</th>
                <th className="px-3 py-3 font-medium">Peak VRAM</th>
                <th className="px-3 py-3 font-medium">Server p50</th>
                <th className="px-3 py-3 font-medium">Server p95</th>
                <th className="px-3 py-3 font-medium">Notes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border bg-surface">
              {HARDWARE.map((h) => (
                <tr key={h.gpu}>
                  <td className="px-4 py-3 font-medium">{h.gpu}</td>
                  <td className="px-3 py-3">
                    <StatusPill tone={h.status === "measured" ? "success" : h.status === "tested" ? "muted" : "soon"}>
                      {h.status === "measured" ? "Measured" : h.status === "tested" ? "Tested" : "Not verified"}
                    </StatusPill>
                  </td>
                  <td className="timecode px-3 py-3">{h.fps ?? "—"}</td>
                  <td className="timecode px-3 py-3">{h.vram ?? "—"}</td>
                  <td className="timecode px-3 py-3">{h.p50 ?? "—"}</td>
                  <td className="timecode px-3 py-3">{h.p95 ?? "—"}</td>
                  <td className="px-3 py-3 text-xs text-muted-foreground">{h.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-border bg-border">
            <div className="bg-surface p-4"><dt className="eyebrow text-[9.5px] text-muted-foreground">Output</dt><dd className="numeral mt-1.5 text-2xl font-medium">{VALIDATION.resolution}</dd></div>
            <div className="bg-surface p-4"><dt className="eyebrow text-[9.5px] text-muted-foreground">Identity (ArcFace)</dt><dd className="numeral mt-1.5 text-2xl font-medium">{VALIDATION.arcface.toFixed(3)}</dd></div>
            <div className="bg-surface p-4"><dt className="eyebrow text-[9.5px] text-muted-foreground">Emotion macro-F1</dt><dd className="numeral mt-1.5 text-2xl font-medium">{VALIDATION.emotionMacroF1.toFixed(3)}</dd></div>
            <div className="bg-surface p-4"><dt className="eyebrow text-[9.5px] text-muted-foreground">Engine</dt><dd className="mt-1.5 text-sm font-medium">TensorRT on L40S</dd></div>
          </dl>
          <div className="space-y-3 text-sm text-muted-foreground">
            <p className="border-l-2 border-ember pl-4">{DISCLAIMER}</p>
            <p className="border-l-2 border-border pl-4">{LATENCY_NOTE}</p>
            <p className="border-l-2 border-border pl-4">The model is not advertised as running at 25 FPS on all hardware. Only measured GPUs carry figures.</p>
          </div>
        </div>
      </section>
    </Page>
  );
}
