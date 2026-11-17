import { createFileRoute } from "@tanstack/react-router";
import { Mic, Send } from "lucide-react";
import { Page, PageHeader } from "@/components/app/PageHeader";
import { DemoNote, SoonBadge } from "@/components/app/Status";
import { useComingSoon } from "@/components/app/ComingSoon";
import { FaceMesh } from "@/components/brand/FaceMesh";
import { CropGuides } from "@/components/brand/HeroStage";
import { WaveformMotif } from "@/components/brand/Waveform";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { faceFor } from "@/lib/emotions";

export const Route = createFileRoute("/app/conversation")({
  head: () => ({
    meta: [
      { title: "AI conversation — EmoStream (coming soon)" },
      {
        name: "description",
        content:
          "Ask a question out loud and your avatar answers. Spoken question → speech processing → LLM → TTS → avatar. Coming soon.",
      },
      { property: "og:title", content: "AI conversation — EmoStream" },
      {
        property: "og:description",
        content: "A spoken conversation with your avatar. Coming soon to EmoStream.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: Conversation,
});

const FLOW = ["Spoken question", "Speech processing", "LLM response", "TTS", "Avatar speaks"];

const EXAMPLE = [
  { who: "you", text: "Can you explain what BehaviourNet does?" },
  {
    who: "avatar",
    text: "It reads speech features from your voice and predicts how the face should move — one branch for the mouth and jaw, another for emotion.",
  },
  { who: "you", text: "Say that again, but happier." },
];

function Conversation() {
  const soon = useComingSoon();
  const explain = () =>
    soon({
      title: "AI conversation",
      body: "There's no conversational backend yet — no transcription, language model or speech provider is connected. This layout shows how a spoken exchange will work.",
      flow: FLOW,
    });

  return (
    <Page wide>
      <PageHeader
        label="Voice sources · AI conversation"
        title="Ask out loud. Your avatar answers."
        description="A spoken conversation workspace. Your question is transcribed, answered by a language model, turned into speech, and spoken by your avatar."
        actions={<SoonBadge />}
      />
      <ol className="mt-6 flex flex-wrap items-center gap-2">
        {FLOW.map((f, i) => (
          <li key={f} className="flex items-center gap-2">
            <span className="timecode rounded border border-border bg-surface px-2.5 py-1 text-[11px] uppercase">
              {f}
            </span>
            {i < FLOW.length - 1 && <span className="h-px w-4 bg-border" />}
          </li>
        ))}
      </ol>

      <div className="mt-6 grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_280px]">
        <section className="stage relative aspect-square overflow-hidden rounded-xl">
          <CropGuides />
          <FaceMesh
            params={faceFor("happy", 40, { mouthOpen: 0.35 })}
            className="absolute inset-[6%] h-[88%] w-[88%]"
            lineClass="stroke-stage-foreground/45"
            dotClass="fill-stage-foreground/40"
            accentClass="stroke-ember/70"
          />
          <div className="absolute inset-x-4 top-4 flex items-center justify-between">
            <span className="eyebrow flex items-center gap-2 text-[10px] text-stage-muted">
              <span className="size-1.5 rounded-full bg-stage-muted" /> Idle · not connected
            </span>
            <span className="eyebrow text-[9px] text-stage-muted">Illustration</span>
          </div>
          <div className="absolute inset-x-4 bottom-4 grid grid-cols-2 gap-2">
            <div className="rounded-md border border-stage-line bg-stage/70 p-2">
              <p className="eyebrow text-[9px] text-stage-muted">Listening</p>
              <WaveformMotif
                bars={32}
                seed={2}
                className="mt-1 h-5 w-full text-stage-foreground/25"
              />
            </div>
            <div className="rounded-md border border-stage-line bg-stage/70 p-2">
              <p className="eyebrow text-[9px] text-stage-muted">Speaking</p>
              <WaveformMotif
                bars={32}
                seed={5}
                className="mt-1 h-5 w-full text-stage-foreground/25"
              />
            </div>
          </div>
        </section>

        <section className="panel flex flex-col p-5">
          <div className="flex items-center justify-between">
            <p className="eyebrow text-muted-foreground">Conversation</p>
            <DemoNote>Example layout · not a real exchange</DemoNote>
          </div>
          <ul className="mt-4 flex-1 space-y-3">
            {EXAMPLE.map((m, i) => (
              <li
                key={i}
                className={
                  m.who === "you"
                    ? "ml-8 rounded-lg rounded-br-sm bg-sunk p-3 text-sm"
                    : "mr-8 rounded-lg rounded-bl-sm border border-border p-3 font-display text-lg leading-snug"
                }
              >
                <p className="eyebrow mb-1 text-[9px] text-muted-foreground">
                  {m.who === "you" ? "You" : "Avatar"}
                </p>
                {m.text}
              </li>
            ))}
          </ul>
          <div className="mt-4 flex gap-2">
            <Button variant="live" size="icon" onClick={explain} aria-label="Hold to talk">
              <Mic />
            </Button>
            <Input placeholder="Or type a question" onFocus={explain} readOnly />
            <Button variant="ink" size="icon" onClick={explain} aria-label="Send">
              <Send />
            </Button>
          </div>
        </section>

        <aside className="panel soon-surface space-y-4 p-5">
          <p className="eyebrow text-muted-foreground">Configuration</p>
          <Labeled label="LLM provider">
            <Select defaultValue="none">
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Not configured</SelectItem>
              </SelectContent>
            </Select>
          </Labeled>
          <Labeled label="Model">
            <Select defaultValue="none" disabled>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Choose a provider first</SelectItem>
              </SelectContent>
            </Select>
          </Labeled>
          <Labeled label="TTS voice">
            <Select defaultValue="warm">
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="warm">Warm · mid</SelectItem>
                <SelectItem value="clear">Clear · bright</SelectItem>
              </SelectContent>
            </Select>
          </Labeled>
          <div>
            <p className="eyebrow mb-2 text-[10px] text-muted-foreground">History</p>
            <p className="text-xs text-muted-foreground">
              Past conversations will be listed here once they can be stored.
            </p>
          </div>
          <Button variant="hairline" className="w-full" onClick={explain}>
            Connect a provider
          </Button>
        </aside>
      </div>
    </Page>
  );
}

function Labeled({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-1.5 text-xs font-medium">{label}</p>
      {children}
    </div>
  );
}
