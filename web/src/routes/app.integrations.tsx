import { createFileRoute } from "@tanstack/react-router";
import { ArrowUpRight } from "lucide-react";
import { useState } from "react";
import { Page, PageHeader } from "@/components/app/PageHeader";
import { StatusPill } from "@/components/app/Status";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/app/integrations")({
  head: () => ({
    meta: [
      { title: "Integrations — EmoStream" },
      {
        name: "description",
        content:
          "Where EmoStream could plug in: meetings, real-time media, SDKs, text-to-speech and language models. Status shown honestly.",
      },
      { property: "og:title", content: "Integrations — EmoStream" },
      { property: "og:description", content: "EmoStream's available and planned connectors." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: Integrations,
});

type St = "available" | "planned" | "soon";
interface Integration {
  name: string;
  mono: string;
  group: "Engine" | "Meetings" | "Real-time media" | "Developers" | "Voice & language";
  status: St;
  summary: string;
  how: string;
}

const LIST: Integration[] = [
  {
    name: "Engine session API",
    mono: "WS",
    group: "Engine",
    status: "available",
    summary: "WebSocket /ws/session, plus /api/info and /api/export.",
    how: "This is what Studio uses today: microphone audio streams in, H.264 video frames stream back. By default Studio uses the engine that serves this page; Settings → Performance can point it at another one. The contract is documented in docs/integration/frontend_backend_contract.md.",
  },
  {
    name: "Custom API",
    mono: "{ }",
    group: "Developers",
    status: "planned",
    summary: "Documented REST + WebSocket contract for your own apps.",
    how: "A stable, versioned description of the session protocol so other software can drive an avatar without the Studio UI.",
  },
  {
    name: "JavaScript SDK",
    mono: "JS",
    group: "Developers",
    status: "planned",
    summary: "Drop-in client for browsers: mic capture, streaming, frame display.",
    how: "Would package the Studio's audio capture and frame rendering into a small library you can import into any web page.",
  },
  {
    name: "WebRTC",
    mono: "RTC",
    group: "Real-time media",
    status: "planned",
    summary: "Low-latency media transport instead of WebSocket frames.",
    how: "Would carry audio and video over a peer connection, reducing delay and handling poor networks better than per-frame images.",
  },
  {
    name: "LiveKit",
    mono: "LK",
    group: "Real-time media",
    status: "planned",
    summary: "Publish the avatar as a participant in a LiveKit room.",
    how: "The engine would join a room as a video track, so any LiveKit-based app could show the avatar.",
  },
  {
    name: "Google Meet",
    mono: "GM",
    group: "Meetings",
    status: "soon",
    summary: "Appear in calls as your animated avatar.",
    how: "Likely through a virtual camera: the avatar stream becomes a webcam source the meeting app can select. No connection to Google exists today.",
  },
  {
    name: "Zoom",
    mono: "ZM",
    group: "Meetings",
    status: "soon",
    summary: "Use the avatar as your video in Zoom meetings.",
    how: "Same virtual-camera approach as Meet. Nothing is connected to Zoom yet.",
  },
  {
    name: "Microsoft Teams",
    mono: "MT",
    group: "Meetings",
    status: "soon",
    summary: "Use the avatar as your video in Teams.",
    how: "Same virtual-camera approach. Nothing is connected to Microsoft yet.",
  },
  {
    name: "TTS providers",
    mono: "TTS",
    group: "Voice & language",
    status: "soon",
    summary: "Generate speech from text, then animate it.",
    how: "Text goes to a speech provider, the audio comes back and drives the avatar exactly like a microphone would. See Text to speech.",
  },
  {
    name: "LLM providers",
    mono: "LLM",
    group: "Voice & language",
    status: "soon",
    summary: "Let the avatar answer spoken questions.",
    how: "Speech → transcription → language model → TTS → avatar. See AI conversation.",
  },
];

const LABEL: Record<St, string> = {
  available: "Available",
  planned: "Planned",
  soon: "Coming soon",
};

function Integrations() {
  const [filter, setFilter] = useState<St | "all">("all");
  const [open, setOpen] = useState<Integration | null>(null);
  const shown = LIST.filter((i) => filter === "all" || i.status === filter);
  const groups = Array.from(new Set(shown.map((i) => i.group)));

  return (
    <Page wide>
      <PageHeader
        label="Ecosystem · Integrations"
        title="Where EmoStream could plug in"
        description="One connection works today: the engine's own session API. Everything else is a plan, and is labelled as one. No accounts are connected and no sign-in flows exist for third-party services."
      />
      <div className="mt-6 flex flex-wrap gap-1.5" role="tablist" aria-label="Filter by status">
        {(["all", "available", "planned", "soon"] as const).map((f) => (
          <button
            key={f}
            role="tab"
            aria-selected={filter === f}
            onClick={() => setFilter(f)}
            className={cn(
              "rounded-full border px-3.5 py-1.5 text-[13px] transition-colors",
              filter === f
                ? "border-foreground bg-foreground text-background"
                : "border-border hover:border-foreground/40",
            )}
          >
            {f === "all" ? "All" : LABEL[f]}{" "}
            <span className="timecode ml-1 text-[10px] opacity-60">
              {f === "all" ? LIST.length : LIST.filter((i) => i.status === f).length}
            </span>
          </button>
        ))}
      </div>

      <div className="mt-8 space-y-10">
        {groups.map((g) => (
          <section key={g}>
            <p className="eyebrow mb-3 text-muted-foreground">{g}</p>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {shown
                .filter((i) => i.group === g)
                .map((i) => (
                  <button
                    key={i.name}
                    onClick={() => setOpen(i)}
                    className={cn(
                      "group panel flex gap-4 p-5 text-left transition-[border-color,transform] duration-200 ease-soft hover:-translate-y-px hover:border-foreground/30",
                      i.status !== "available" && "soon-surface",
                    )}
                  >
                    <span
                      className={cn(
                        "timecode flex size-12 shrink-0 items-center justify-center rounded-md border text-[12px] font-medium",
                        i.status === "available"
                          ? "stage-band border-transparent text-stage-foreground"
                          : "border-border bg-surface text-muted-foreground",
                      )}
                    >
                      {i.mono}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center justify-between gap-2">
                        <span className="font-semibold">{i.name}</span>
                        <ArrowUpRight className="size-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
                      </span>
                      <span className="mt-1 block text-[13px] leading-snug text-muted-foreground">
                        {i.summary}
                      </span>
                      <span className="mt-3 block">
                        <StatusPill
                          tone={i.status === "available" ? "success" : "soon"}
                          dot={i.status === "available"}
                        >
                          {LABEL[i.status]}
                        </StatusPill>
                      </span>
                    </span>
                  </button>
                ))}
            </div>
          </section>
        ))}
      </div>
      <p className="mt-10 text-xs text-muted-foreground">
        Third-party names are used only to describe compatibility goals. Logos are not shown because
        no partnership or permission exists.
      </p>

      <Dialog open={!!open} onOpenChange={(o) => !o && setOpen(null)}>
        <DialogContent className="max-w-md">
          {open && (
            <DialogHeader>
              <div>
                <StatusPill tone={open.status === "available" ? "success" : "soon"}>
                  {LABEL[open.status]}
                </StatusPill>
              </div>
              <DialogTitle className="font-display text-3xl font-normal">{open.name}</DialogTitle>
              <DialogDescription className="text-[15px] leading-relaxed">
                {open.how}
              </DialogDescription>
            </DialogHeader>
          )}
        </DialogContent>
      </Dialog>
    </Page>
  );
}
