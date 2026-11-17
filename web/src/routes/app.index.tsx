import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowRight, Info } from "lucide-react";
import { FrameStrip } from "@/components/brand/FrameStrip";
import { Page, SectionTitle } from "@/components/app/PageHeader";
import { StatusPill } from "@/components/app/Status";
import { Button } from "@/components/ui/button";
import { CURRENT, DISCLAIMER, VALIDATION } from "@/lib/benchmarks";
import { emotionById } from "@/lib/emotions";
import { useEngineStatus } from "@/lib/engine/useEngineStatus";
import { duration } from "@/lib/format";
import { useSettings } from "@/lib/settings";
import { useStudio } from "@/lib/studio-store";

export const Route = createFileRoute("/app/")({
  head: () => ({
    meta: [
      { title: "Overview — EmoStream" },
      {
        name: "description",
        content:
          "Your EmoStream workspace: engine status, current configuration, benchmarks and what's in development.",
      },
      { property: "og:title", content: "Overview — EmoStream" },
      {
        property: "og:description",
        content: "Engine status, configuration and development status for EmoStream.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: Overview,
});

const FEATURES: {
  name: string;
  status: "available" | "engine" | "planned" | "soon";
  note: string;
}[] = [
  {
    name: "Live microphone input",
    status: "available",
    note: "Captured in the browser, streamed as 16 kHz PCM",
  },
  {
    name: "Emotion + intensity control",
    status: "available",
    note: "Five emotions, 0–100%, adjustable mid-session",
  },
  { name: "Rendered avatar stream", status: "engine", note: "Needs a running EmoStream engine" },
  { name: "Export of a take", status: "engine", note: "Through the engine's /api/export" },
  { name: "Audio file input", status: "planned", note: "Not confirmed on the current engine" },
  {
    name: "Saved avatars & session history",
    status: "planned",
    note: "Engine does not persist anything yet",
  },
  { name: "Text to speech", status: "soon", note: "Text → TTS → audio → animation" },
  { name: "AI conversation", status: "soon", note: "Speech → LLM → TTS → avatar speaks" },
  { name: "Meeting integrations", status: "soon", note: "Meet, Zoom, Teams via virtual camera" },
];

function Overview() {
  const settings = useSettings((s) => s);
  const sessions = useStudio((s) => s.sessions);
  const portrait = useStudio((s) => s.portrait);
  const avatarName = useStudio((s) => s.avatarName);
  const { status, info } = useEngineStatus();
  const emo = emotionById(settings.defaultEmotion);

  return (
    <Page wide>
      <p className="eyebrow text-muted-foreground">Overview</p>
      <div className="mt-5 grid gap-5 xl:grid-cols-[1.55fr_1fr]">
        {/* Primary action */}
        <section className="stage grain relative overflow-hidden rounded-xl">
          <div className="hairline-grid absolute inset-0 opacity-30" aria-hidden />
          <div className="relative z-[2] grid gap-8 p-7 md:grid-cols-[1.1fr_1fr] md:p-9">
            <div className="flex flex-col">
              <p className="eyebrow text-stage-muted">Studio</p>
              <h1 className="display-lg mt-4 text-stage-foreground">
                {portrait ? "Pick up where you left off." : "One portrait. One voice."}
              </h1>
              <p className="mt-4 max-w-sm text-[15px] text-stage-muted">
                {portrait
                  ? `“${avatarName}” is loaded. Start speaking to preview the animation.`
                  : "Upload a portrait, choose an emotion, and start speaking. Everything happens in one workspace."}
              </p>
              <div className="mt-auto pt-8">
                <Button asChild variant="ember" size="lg">
                  <Link to="/app/studio">
                    Open Studio <ArrowRight />
                  </Link>
                </Button>
              </div>
            </div>
            <div className="self-end">
              <FrameStrip frames={4} start={140} emotion="happy" intensity={50} />
              <p className="eyebrow mt-2 text-[9px] text-stage-muted">
                Diagram · articulation frames
              </p>
            </div>
          </div>
        </section>

        {/* Engine + configuration */}
        <section className="panel flex flex-col p-6">
          <SectionTitle
            label="Engine"
            title={
              status === "online"
                ? "Connected"
                : status === "offline"
                  ? "Unreachable"
                  : status === "checking"
                    ? "Checking…"
                    : "Not connected"
            }
            aside={
              <StatusPill
                tone={status === "online" ? "success" : status === "offline" ? "live" : "muted"}
                dot
                pulse={status === "checking"}
              >
                {status === "unset" ? "No address" : status}
              </StatusPill>
            }
          />
          <p className="text-sm text-muted-foreground">
            {status === "unset"
              ? "No engine address is available."
              : status === "online"
                ? `/api/info answered in ${info?.latencyMs ?? "—"} ms.`
                : (info?.error ?? "Waiting for /api/info.")}
          </p>
          <dl className="mt-5 divide-y divide-border border-y border-border text-sm">
            <Row k="Default emotion" v={`${emo.label} · ${settings.defaultIntensity}%`} />
            <Row k="Output" v={`${VALIDATION.resolution} · watermark on`} />
            <Row k="Microphone" v={settings.micDeviceId ? "Selected device" : "System default"} />
            <Row k="Engine address" v={settings.engineUrl || "This site"} mono />
          </dl>
          <div className="mt-auto flex gap-2 pt-5">
            <Button asChild variant="hairline" size="sm">
              <Link to="/app/settings" hash="performance">
                Engine settings
              </Link>
            </Button>
            <Button asChild variant="ghost" size="sm">
              <Link to="/app/settings">All settings</Link>
            </Button>
          </div>
        </section>
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-[1fr_1.55fr]">
        {/* Notices + activity */}
        <div className="space-y-5">
          <section className="panel p-6">
            <SectionTitle label="Notices" title="Before you start" />
            <ul className="space-y-3 text-sm">
              <Notice>
                Sessions and avatars live only in this browser tab. Closing it clears them.
              </Notice>
              <Notice>
                Every preview frame carries a visible “AI-generated” watermark. It can't be turned
                off.
              </Notice>
              <Notice>
                RTX 4050 performance hasn't been verified. Headline figures come from an L40S.
              </Notice>
            </ul>
          </section>
          <section className="panel p-6">
            <SectionTitle label="Recent activity" title="This visit" />
            {sessions.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No takes yet. Activity from this visit shows here — nothing is stored on a server.
              </p>
            ) : (
              <ul className="divide-y divide-border">
                {sessions.slice(0, 4).map((s) => (
                  <li key={s.id} className="flex items-center justify-between py-2.5 text-sm">
                    <span className="truncate">{s.avatarName}</span>
                    <span className="timecode text-xs text-muted-foreground">
                      {duration(s.durationMs)} · {emotionById(s.finalEmotion).label}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        <div className="space-y-5">
          {/* Benchmark snapshot */}
          <section className="panel p-6">
            <SectionTitle
              label="Benchmark snapshot"
              title={`Live model ${CURRENT.model} · engine run ${VALIDATION.date}`}
              aside={
                <Link
                  to="/app/models"
                  className="text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                >
                  Conditions & hardware
                </Link>
              }
            />
            <dl className="grid grid-cols-3 gap-px overflow-hidden rounded-lg border border-border bg-border sm:grid-cols-6">
              {[
                ["FPS", "≈25"],
                ["p50", `${VALIDATION.serverP50Ms}ms`],
                ["p95", `${VALIDATION.serverP95Ms}ms`],
                ["VRAM", `${VALIDATION.peakVramGiB}GiB`],
                ["ArcFace", CURRENT.arcface.toFixed(3)],
                ["SyncNet", CURRENT.lseC.toFixed(2)],
              ].map(([k, v]) => (
                <div key={k} className="bg-surface p-3">
                  <dt className="eyebrow text-[9px] text-muted-foreground">{k}</dt>
                  <dd className="numeral mt-1.5 text-lg font-medium">{v}</dd>
                </div>
              ))}
            </dl>
            <p className="mt-3 flex gap-2 text-xs leading-relaxed text-muted-foreground">
              <Info className="mt-0.5 size-3.5 shrink-0" /> {DISCLAIMER} FPS, latency and memory:
              engine run on an L40S, {VALIDATION.date} (earlier model {VALIDATION.model}); latency
              is server-side only. ArcFace and SyncNet confidence (LSE-C): live model{" "}
              {CURRENT.model}, 80 MEAD validation clips, {CURRENT.date}.
            </p>
          </section>

          {/* Development status */}
          <section className="panel p-6">
            <SectionTitle label="Development status" title="What works today, and what's next" />
            <ul className="divide-y divide-border">
              {FEATURES.map((f) => (
                <li
                  key={f.name}
                  className="grid grid-cols-[1fr_auto] items-center gap-3 py-2.5 sm:grid-cols-[1.1fr_1.4fr_auto]"
                >
                  <span className="text-sm font-medium">{f.name}</span>
                  <span className="hidden text-xs text-muted-foreground sm:block">{f.note}</span>
                  <StatusPill
                    tone={
                      f.status === "available"
                        ? "success"
                        : f.status === "engine"
                          ? "warning"
                          : "soon"
                    }
                  >
                    {f.status === "available"
                      ? "Available"
                      : f.status === "engine"
                        ? "Needs engine"
                        : f.status === "planned"
                          ? "Planned"
                          : "Coming soon"}
                  </StatusPill>
                </li>
              ))}
            </ul>
          </section>
        </div>
      </div>
    </Page>
  );
}

function Row({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2.5">
      <dt className="text-muted-foreground">{k}</dt>
      <dd className={mono ? "timecode truncate text-xs" : "font-medium"}>{v}</dd>
    </div>
  );
}

function Notice({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex gap-3">
      <span className="mt-2 h-px w-3 shrink-0 bg-ember" />
      <span className="text-muted-foreground">{children}</span>
    </li>
  );
}
