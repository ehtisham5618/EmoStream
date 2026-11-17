import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { AvatarStage } from "@/components/studio/AvatarStage";
import { EmotionPanel } from "@/components/studio/EmotionPanel";
import { PortraitPanel } from "@/components/studio/PortraitPanel";
import { SessionPanel } from "@/components/studio/SessionPanel";
import { Timeline } from "@/components/studio/Timeline";
import { VoicePanel } from "@/components/studio/VoicePanel";
import { useStudioSession } from "@/components/studio/useStudioSession";

export const Route = createFileRoute("/app/studio")({
  head: () => ({
    meta: [
      { title: "Studio — EmoStream" },
      {
        name: "description",
        content:
          "Upload a portrait, speak, and choose an emotion. The EmoStream Studio turns your voice into facial motion.",
      },
      { property: "og:title", content: "Studio — EmoStream" },
      { property: "og:description", content: "Portrait → audio → emotion → animated avatar." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: Studio,
});

const FLOW = ["Portrait", "Audio", "Emotion", "Animated avatar"];

function Studio() {
  const [preparing, setPreparing] = useState(false);
  const s = useStudioSession({ preparing });
  const live = s.phase === "running" || s.phase === "paused";
  const stepDone = [
    s.stage !== "empty" && s.stage !== "preparing",
    s.mic.state === "recording" || s.phase === "complete",
    true,
    s.stage === "active" || (s.phase === "complete" && s.stats.framesReceived > 0),
  ];

  return (
    <div className="mx-auto w-full max-w-[1600px] px-4 py-5 md:px-6">
      <header className="mb-4 flex flex-wrap items-center gap-x-6 gap-y-3">
        <div>
          <p className="eyebrow text-muted-foreground">Studio</p>
          <h1 className="font-display text-[2rem] leading-none">Give your portrait a voice.</h1>
        </div>
        <ol className="ml-auto flex flex-wrap items-center gap-1.5" aria-label="Workflow">
          {FLOW.map((f, i) => (
            <li key={f} className="flex items-center gap-1.5">
              <span
                className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11.5px] transition-colors ${stepDone[i] ? "border-foreground/20 bg-surface text-foreground" : "border-border text-muted-foreground"}`}
              >
                <span className="timecode text-[10px] text-ember">0{i + 1}</span> {f}
              </span>
              {i < FLOW.length - 1 && <span className="h-px w-3 bg-border" />}
            </li>
          ))}
        </ol>
      </header>

      <div className="grid gap-4 lg:grid-cols-[284px_minmax(0,1fr)] xl:grid-cols-[284px_minmax(0,1fr)_304px]">
        <div className="order-2 space-y-4 lg:order-1 lg:row-span-2 xl:row-span-1">
          <PortraitPanel preparing={preparing} setPreparing={setPreparing} locked={live} />
          <VoicePanel s={s} />
        </div>
        <div className="order-1 min-w-0 lg:order-2">
          <AvatarStage s={s} />
        </div>
        <div className="order-3 grid gap-4 sm:grid-cols-2 lg:col-start-2 xl:col-start-auto xl:block xl:space-y-4">
          <EmotionPanel live={live} />
          <SessionPanel s={s} />
        </div>
        <div className="order-4 lg:col-span-2 xl:col-span-3">
          <Timeline s={s} />
        </div>
      </div>
    </div>
  );
}
