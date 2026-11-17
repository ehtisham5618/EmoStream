import { createFileRoute, Link } from "@tanstack/react-router";
import { Page, PageHeader, SectionTitle } from "@/components/app/PageHeader";
import { ExpressionGlyph } from "@/components/brand/ExpressionGlyph";
import { PipelineDiagram } from "@/components/brand/PipelineDiagram";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { CURRENT, DISCLAIMER, MODEL } from "@/lib/benchmarks";
import { EMOTIONS } from "@/lib/emotions";

export const Route = createFileRoute("/app/help")({
  head: () => ({
    meta: [
      { title: "About & Help — EmoStream" },
      {
        name: "description",
        content:
          "How EmoStream works, its model, supported emotions, research goals, responsible-AI practices, licensing, API notes and FAQs.",
      },
      { property: "og:title", content: "About & Help — EmoStream" },
      { property: "og:description", content: "Documentation and answers for EmoStream." },
      { property: "og:type", content: "article" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: Help,
});

const TOC = [
  ["overview", "Project overview"],
  ["how", "How it works"],
  ["architecture", "Technical architecture"],
  ["model", "Current model"],
  ["emotions", "Supported emotions"],
  ["research", "Research objectives"],
  ["responsible", "Responsible AI"],
  ["licensing", "Licensing"],
  ["docs", "Documentation"],
  ["faq", "FAQs"],
] as const;

const FAQ: [string, string][] = [
  [
    "Why does the preview show my photo without moving?",
    "Animation is produced by the EmoStream engine, not the browser. Without an engine address in Settings, Studio still captures your voice and timeline, but shows the portrait still. That's deliberate: we don't fake motion with zoom or wobble effects.",
  ],
  [
    "Can I change the emotion while I'm talking?",
    "Yes. Emotion and intensity are sent to the engine as soon as you change them, and the timeline marks each change. Articulation keeps following your voice.",
  ],
  [
    "What makes a good portrait?",
    "One person, facing the camera, evenly lit, with eyes and mouth visible. At least 512×512 pixels. Avoid heavy filters, sunglasses and hands near the face.",
  ],
  [
    "Is my portrait uploaded?",
    "Only when you start a session with an engine connected: a 512×512 crop is sent to that engine. Otherwise it stays in this browser tab and is discarded when you close it.",
  ],
  [
    "How fast is it on my computer?",
    "We don't know yet. The ≈25 FPS figure was measured on an NVIDIA L40S with TensorRT. RTX 4050 performance hasn't been verified, and other GPUs may be slower.",
  ],
  [
    "Is the 269 ms server latency what I'll feel?",
    "No. It's measured on the server (15 Nov engine run). Network transit, buffering, decoding and display all add to it; the Studio timeline shows the avatar's actual delay in your session.",
  ],
  [
    "Can I export a video?",
    "After a rendered take, Export asks the engine's /api/export for the file. Export isn't available without an engine.",
  ],
  [
    "Can I remove the AI-generated watermark?",
    "No. Every output is labelled so viewers know it isn't a real recording.",
  ],
];

function Help() {
  return (
    <Page wide>
      <PageHeader
        label="Preferences · About & Help"
        title="About EmoStream, and how to use it"
        description="Plain explanations of what the system does, where its limits are, and how the interface talks to the engine."
      />
      <div className="mt-8 grid gap-10 lg:grid-cols-[200px_minmax(0,1fr)]">
        <nav className="hidden lg:block" aria-label="Contents">
          <ul className="sticky top-8 space-y-px border-l border-border">
            {TOC.map(([id, l], i) => (
              <li key={id}>
                <a
                  href={`#${id}`}
                  className="-ml-px flex gap-3 border-l border-transparent py-1.5 pl-4 text-sm text-muted-foreground hover:border-foreground hover:text-foreground"
                >
                  <span className="timecode text-[10px] text-ember">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  {l}
                </a>
              </li>
            ))}
          </ul>
        </nav>
        <article className="max-w-3xl space-y-14 text-[15px] leading-relaxed">
          <S id="overview" title="Project overview">
            <p>
              EmoStream animates a single portrait from live speech. You give it one photo and your
              voice; it returns a 512×512 video of that face speaking, with lips, jaw, eyes, brows
              and head moving in time. A separate control sets the emotion the face shows, and how
              strongly.
            </p>
            <p>
              It's an academic research project, not a commercial service. The interface you're
              using is designed to show exactly what the system can do today, and to make clear what
              is still planned.
            </p>
          </S>
          <S id="how" title="How it works">
            <ol className="space-y-3">
              {[
                "Upload a portrait, crop it, and confirm consent.",
                "Start a session. Your microphone audio streams to the engine in small chunks.",
                "Choose an emotion and intensity — before or during the session.",
                "The engine sends back rendered frames, which appear in the preview with a watermark.",
                "Stop the session and, if an engine rendered it, export the take.",
              ].map((t, i) => (
                <li key={t} className="flex gap-4">
                  <span className="timecode mt-0.5 text-xs text-ember">0{i + 1}</span>
                  {t}
                </li>
              ))}
            </ol>
          </S>
          <S id="architecture" title="Technical architecture">
            <PipelineDiagram />
            <p>
              The portrait is turned into an appearance representation once. Audio passes through
              WavLM for speech features, then BehaviourNet predicts motion in two branches:
              articulation (driven by audio) and emotion (driven by your selection). Motion fusion
              combines them, and the frozen LivePortrait renderer produces each frame.
            </p>
          </S>
          <S id="model" title="Current model">
            <p>
              <strong>{MODEL.name}</strong> — {MODEL.params} parameters. {MODEL.facts.join(" ")}
            </p>
            <p>
              Renderer: {MODEL.renderer}. See{" "}
              <Link to="/app/models" className="underline underline-offset-2">
                Models & Performance
              </Link>{" "}
              for figures and conditions.
            </p>
          </S>
          <S id="emotions" title="Supported emotions">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
              {EMOTIONS.map((e) => (
                <div key={e.id} className="panel p-3 text-center">
                  <ExpressionGlyph
                    emotion={e.id}
                    className="mx-auto h-14 w-full text-foreground/70"
                  />
                  <p className="mt-2 text-sm font-medium">{e.label}</p>
                  <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">{e.cue}</p>
                </div>
              ))}
            </div>
            <p>
              Intensity runs from 0% (no visible emotion) to 100% (the strongest expression the
              model was trained on). The expression diagrams here are drawings, not model output.
            </p>
          </S>
          <S id="research" title="Research objectives">
            <ul className="list-none space-y-2">
              {[
                `Run in real time with a small trained model (${MODEL.params} parameters) on a single GPU.`,
                `Keep the person recognisable while they speak (identity similarity, ArcFace ${CURRENT.arcface.toFixed(3)} for the live model).`,
                `Make emotion controllable and measurable (macro-F1 ${CURRENT.emotionMacroF1.toFixed(3)} across five classes, live model).`,
                "Stay causal, so the animation can stream without waiting for the end of a sentence.",
              ].map((t) => (
                <li key={t} className="flex gap-3">
                  <span className="mt-2.5 h-px w-3 shrink-0 bg-ember" />
                  {t}
                </li>
              ))}
            </ul>
            <p className="text-sm text-muted-foreground">{DISCLAIMER}</p>
          </S>
          <S id="responsible" title="Responsible AI">
            <p>
              Animated faces can mislead. EmoStream's interface requires a consent confirmation for
              every portrait, always draws an “AI-generated” watermark on the preview, and doesn't
              store portraits beyond the open tab. Don't animate someone without their permission,
              and don't present output as real footage.
            </p>
            <p>
              Read the full{" "}
              <Link to="/responsible-ai" className="underline underline-offset-2">
                Responsible AI
              </Link>{" "}
              and{" "}
              <Link to="/privacy" className="underline underline-offset-2">
                Privacy
              </Link>{" "}
              notes.
            </p>
          </S>
          <S id="licensing" title="Licensing">
            <p>
              EmoStream builds on third-party work — WavLM, LivePortrait and the Ditto packaging,
              and the MEAD dataset for training — each under its own licence and terms. Some of
              these restrict commercial use. Check each component's licence before using EmoStream
              output beyond research.
            </p>
          </S>
          <S id="docs" title="Documentation">
            <p>The interface talks to an engine through three endpoints:</p>
            <dl className="divide-y divide-border rounded-lg border border-border bg-surface">
              {(
                [
                  [
                    "WS /ws/session",
                    "Live session: portrait and settings in, audio chunks in, rendered frames and stats out.",
                  ],
                  [
                    "GET /api/info",
                    "Engine details — model, GPU, version. Shown on Models & Performance.",
                  ],
                  ["POST /api/export", "Returns the finished take as a video file."],
                ] as [string, string][]
              ).map(([k, v]) => (
                <div key={k} className="grid gap-1 p-4 sm:grid-cols-[170px_1fr]">
                  <dt className="timecode text-[13px] font-medium">{k}</dt>
                  <dd className="text-sm text-muted-foreground">{v}</dd>
                </div>
              ))}
            </dl>
            <p className="text-sm text-muted-foreground">
              The message format the interface sends is an assumption until it's checked against the
              engine's source. It's kept in one adapter so it can be corrected without touching the
              rest of the app.
            </p>
          </S>
          <S id="faq" title="FAQs">
            <Accordion
              type="single"
              collapsible
              className="rounded-lg border border-border bg-surface px-4"
            >
              {FAQ.map(([q, a]) => (
                <AccordionItem key={q} value={q}>
                  <AccordionTrigger className="text-left text-[15px]">{q}</AccordionTrigger>
                  <AccordionContent className="text-muted-foreground">{a}</AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </S>
        </article>
      </div>
    </Page>
  );
}

function S({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="scroll-mt-8 space-y-4">
      <SectionTitle title={<span className="font-display text-[2rem] font-normal">{title}</span>} />
      {children}
    </section>
  );
}
