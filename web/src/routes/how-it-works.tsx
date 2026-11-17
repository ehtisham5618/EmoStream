import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowRight } from "lucide-react";
import { ExpressionGlyph } from "@/components/brand/ExpressionGlyph";
import { FrameStrip } from "@/components/brand/FrameStrip";
import { CropGuides } from "@/components/brand/HeroStage";
import { PipelineDiagram } from "@/components/brand/PipelineDiagram";
import { WaveformMotif } from "@/components/brand/Waveform";
import { PageIntro, SectionLabel, SiteLayout } from "@/components/site/SiteLayout";
import { Button } from "@/components/ui/button";

export const Route = createFileRoute("/how-it-works")({
  head: () => ({
    meta: [
      { title: "How it works — EmoStream" },
      {
        name: "description",
        content:
          "From one portrait and a live voice to a 512×512 talking avatar: WavLM, BehaviourNet and LivePortrait, step by step.",
      },
      { property: "og:title", content: "How EmoStream works" },
      {
        property: "og:description",
        content: "Portrait → voice → emotion → animated avatar, explained step by step.",
      },
      { property: "og:type", content: "article" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: HowItWorks,
});

function HowItWorks() {
  return (
    <SiteLayout>
      <PageIntro
        label="How it works"
        title={
          <>
            Four steps, one stream. <em className="text-ember">Nothing pre-recorded.</em>
          </>
        }
      >
        EmoStream never needs a video of the person. It reads one portrait, listens to speech as it
        arrives, and predicts the motion for each frame.
      </PageIntro>

      <div className="mx-auto max-w-[1320px] space-y-24 px-5 py-20 md:px-8">
        <Step
          n="01"
          title="Start with a portrait."
          body="A single front-facing photo. You crop it to a square; EmoStream encodes the face's appearance once and reuses it for every frame, which is part of why it can run in real time."
        >
          <div className="stage relative mx-auto aspect-square w-full max-w-sm overflow-hidden rounded-xl">
            <CropGuides />
            <svg viewBox="0 0 100 100" className="absolute inset-0 h-full w-full" aria-hidden>
              <ellipse
                cx="50"
                cy="44"
                rx="20"
                ry="26"
                fill="none"
                className="stroke-stage-foreground/50"
                strokeDasharray="1.5 2"
                strokeWidth="0.5"
              />
              <path
                d="M16 100c4-18 16-26 34-26s30 8 34 26"
                fill="none"
                className="stroke-stage-foreground/35"
                strokeWidth="0.5"
              />
            </svg>
            <span className="eyebrow absolute bottom-4 left-4 text-[9px] text-stage-muted">
              Crop guide · 512×512
            </span>
          </div>
        </Step>
        <Step
          n="02"
          title="Supply your voice."
          body="Speak into your microphone. Audio is sent in small chunks at 16 kHz; WavLM turns it into speech features, and BehaviourNet — causal by design — predicts motion from what it has heard so far."
          flip
        >
          <div className="panel p-6">
            <WaveformMotif bars={90} seed={13} className="h-16 w-full text-foreground/70" />
            <div className="mt-3 flex justify-between">
              {["chunk 01", "chunk 02", "chunk 03", "chunk 04"].map((c) => (
                <span key={c} className="timecode text-[10px] text-muted-foreground">
                  {c}
                </span>
              ))}
            </div>
          </div>
        </Step>
        <Step
          n="03"
          title="Shape the expression."
          body="Choose neutral, happy, sad, angry or surprised, and set intensity from 0 to 100%. The emotion branch changes brows, eyes and mouth shape; articulation keeps following your voice. You can change it mid-sentence."
        >
          <div className="grid grid-cols-5 gap-2">
            {[0, 25, 50, 75, 100].map((i) => (
              <div key={i} className="panel p-2 text-center">
                <ExpressionGlyph
                  emotion="happy"
                  intensity={i}
                  className="h-16 w-full text-foreground/75"
                />
                <span className="timecode text-[10px] text-muted-foreground">{i}%</span>
              </div>
            ))}
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            Diagram: “happy” at five intensities.
          </p>
        </Step>
        <Step
          n="04"
          title="Watch the portrait come alive."
          body="Motion fusion combines appearance with predicted motion, and the frozen LivePortrait renderer draws each 512×512 frame. Frames stream back to your browser, each carrying an AI-generated watermark."
          flip
        >
          <div className="stage rounded-xl p-4">
            <FrameStrip frames={5} start={200} emotion="happy" intensity={45} />
          </div>
        </Step>

        <section>
          <SectionLabel index="ES—05">The whole pipeline</SectionLabel>
          <h2 className="display-md mt-5 mb-8">One small trained model between two frozen ones.</h2>
          <PipelineDiagram />
        </section>

        <div className="flex flex-wrap items-center justify-between gap-6 rounded-xl border border-border bg-sunk p-8">
          <p className="font-display text-3xl">Start speaking to preview the animation.</p>
          <Button asChild variant="ink" size="lg">
            <Link to="/app/studio">
              Open Studio <ArrowRight />
            </Link>
          </Button>
        </div>
      </div>
    </SiteLayout>
  );
}

function Step({
  n,
  title,
  body,
  children,
  flip,
}: {
  n: string;
  title: string;
  body: string;
  children: React.ReactNode;
  flip?: boolean;
}) {
  return (
    <section className="grid items-center gap-10 lg:grid-cols-2 lg:gap-20">
      <div className={flip ? "lg:order-2" : ""}>
        <span className="timecode text-sm text-ember">{n}</span>
        <h2 className="display-lg mt-4">{title}</h2>
        <p className="mt-5 max-w-lg text-lg leading-relaxed text-muted-foreground">{body}</p>
      </div>
      <div className={flip ? "lg:order-1" : ""}>{children}</div>
    </section>
  );
}
