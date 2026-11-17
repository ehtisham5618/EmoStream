import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowRight, ArrowUpRight } from "lucide-react";
import { HeroStage } from "@/components/brand/HeroStage";
import { ExpressionGlyph } from "@/components/brand/ExpressionGlyph";
import { FrameStrip } from "@/components/brand/FrameStrip";
import { WaveformMotif } from "@/components/brand/Waveform";
import { MotionLine } from "@/components/brand/MotionLine";
import { SectionLabel, SiteLayout } from "@/components/site/SiteLayout";
import { Button } from "@/components/ui/button";
import { EMOTIONS } from "@/lib/emotions";
import { CURRENT, DISCLAIMER, VALIDATION } from "@/lib/benchmarks";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "EmoStream — A face that moves with every word" },
      {
        name: "description",
        content:
          "Turn a single portrait into an expressive talking avatar. EmoStream turns voice into synchronized facial motion, with emotion and intensity under your control.",
      },
      { property: "og:title", content: "EmoStream — A face that moves with every word" },
      {
        property: "og:description",
        content: "One portrait. One voice. Voice-driven facial motion with emotion you control.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Landing,
});

const STEPS = [
  {
    n: "01",
    title: "Start with a portrait.",
    body: "One clear, front-facing photo. EmoStream builds an appearance representation from it once, then reuses it for every frame.",
  },
  {
    n: "02",
    title: "Supply your voice.",
    body: "Speak into your microphone. WavLM reads the audio as it arrives; nothing waits for the sentence to finish.",
  },
  {
    n: "03",
    title: "Shape the expression.",
    body: "Pick one of five emotions and set its intensity. Change it mid-sentence — the expression branch follows.",
  },
  {
    n: "04",
    title: "Watch the portrait come alive.",
    body: "Motion is fused and rendered by LivePortrait into a 512×512 stream, labelled as AI-generated.",
  },
];

function Landing() {
  return (
    <SiteLayout>
      {/* HERO */}
      <section className="paper-light relative overflow-hidden">
        <div className="mx-auto grid max-w-[1320px] gap-12 px-5 pb-20 pt-14 md:px-8 lg:grid-cols-[1.05fr_1fr] lg:gap-16 lg:pb-28 lg:pt-20">
          <div className="flex flex-col justify-center">
            <SectionLabel index="ES—01">Audio-driven portrait animation</SectionLabel>
            <h1 className="display-xl mt-7 text-balance">
              A face that moves with <em className="text-ember">every word.</em>
            </h1>
            <p className="mt-7 max-w-xl text-lg leading-relaxed text-muted-foreground">
              Turn a single portrait into an expressive talking avatar. EmoStream transforms voice
              into synchronized facial motion, with emotion and intensity under your control.
            </p>
            <div className="mt-9 flex flex-wrap gap-3">
              <Button asChild variant="ink" size="lg">
                <Link to="/app/studio">
                  Open EmoStream Studio <ArrowRight />
                </Link>
              </Button>
              <Button asChild variant="hairline" size="lg">
                <Link to="/how-it-works">Explore how it works</Link>
              </Button>
            </div>
            <dl className="mt-12 grid max-w-lg grid-cols-3 gap-6 border-t border-border pt-6">
              <HeroFact k="Input" v="1 portrait + voice" />
              <HeroFact k="Emotions" v="5, with intensity" />
              <HeroFact k="Output" v={VALIDATION.resolution} />
            </dl>
          </div>
          <div className="relative">
            <HeroStage className="mx-auto w-full max-w-[600px]" />
            <p className="mt-3 text-center text-xs text-muted-foreground lg:text-left">
              Illustration of the mechanism. Real rendered output appears in Studio when an engine
              is connected.
            </p>
          </div>
        </div>
      </section>

      {/* MECHANISM */}
      <section className="border-y border-border bg-surface">
        <div className="mx-auto max-w-[1320px] px-5 py-20 md:px-8 lg:py-28">
          <div className="grid gap-8 lg:grid-cols-[1fr_2fr]">
            <div>
              <SectionLabel index="ES—02">The mechanism</SectionLabel>
              <h2 className="display-lg mt-6">Portrait, voice, emotion. Then motion.</h2>
              <p className="mt-5 max-w-sm text-muted-foreground">
                Your voice drives the movement. Your selected emotion shapes the expression. The
                portrait keeps its identity.
              </p>
            </div>
            <ol className="grid gap-px overflow-hidden rounded-xl border border-border bg-border sm:grid-cols-2">
              {STEPS.map((s, i) => (
                <li key={s.n} className="flex flex-col bg-surface p-6 lg:p-8">
                  <div className="flex items-baseline justify-between">
                    <span className="timecode text-sm text-ember">{s.n}</span>
                    <StepGraphic i={i} />
                  </div>
                  <h3 className="font-display mt-6 text-[1.7rem] leading-tight">{s.title}</h3>
                  <p className="mt-3 text-[15px] leading-relaxed text-muted-foreground">{s.body}</p>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </section>

      {/* EMOTION */}
      <section className="mx-auto max-w-[1320px] px-5 py-20 md:px-8 lg:py-28">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <SectionLabel index="ES—03">Choose how it expresses itself</SectionLabel>
            <h2 className="display-lg mt-6 max-w-2xl">Five emotions. One dial for how strongly.</h2>
          </div>
          <p className="max-w-sm text-muted-foreground">
            Voice controls articulation. Your selected emotion controls expression. Both run at the
            same time, on separate branches of the model.
          </p>
        </div>
        <div className="mt-12 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {EMOTIONS.map((e) => (
            <div key={e.id} className="panel group p-5">
              <div className="flex items-center justify-between">
                <span className={cn("size-2 rounded-full", e.bgClass)} />
                <span className="timecode text-[10px] text-muted-foreground">100%</span>
              </div>
              <ExpressionGlyph
                emotion={e.id}
                className="mx-auto mt-4 h-28 w-full text-foreground/75"
                accentClass="stroke-ember"
              />
              <p className="mt-4 font-medium">{e.label}</p>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{e.cue}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ARTICULATION STRIP */}
      <section className="stage-band grain">
        <div className="relative z-[2] mx-auto grid max-w-[1320px] gap-12 px-5 py-20 md:px-8 lg:grid-cols-[1fr_1.4fr] lg:py-24">
          <div>
            <p className="eyebrow text-stage-muted">ES—04 · Articulation, frame by frame</p>
            <h2 className="display-lg mt-6 text-stage-foreground">
              Lips and jaw follow the sound, not a script.
            </h2>
            <p className="mt-5 max-w-md text-stage-muted">
              Each 40 ms of audio becomes one frame of mouth and jaw motion. Because the model is
              causal, it never needs to hear what comes next.
            </p>
            <Link
              to="/capabilities"
              className="mt-8 inline-flex items-center gap-1.5 text-sm text-stage-foreground underline-offset-4 hover:underline"
            >
              See every capability <ArrowUpRight className="size-4" />
            </Link>
          </div>
          <div className="space-y-4">
            <WaveformMotif bars={120} seed={4} className="h-14 w-full text-stage-foreground/60" />
            <FrameStrip frames={6} start={96} />
            <p className="eyebrow text-[10px] text-stage-muted">
              Diagram · landmark states sampled every third frame
            </p>
          </div>
        </div>
      </section>

      {/* RESEARCH */}
      <section className="mx-auto max-w-[1320px] px-5 py-20 md:px-8 lg:py-28">
        <div className="grid gap-10 lg:grid-cols-[1fr_1.6fr]">
          <div>
            <SectionLabel index="ES—05">Measured, with conditions</SectionLabel>
            <h2 className="display-lg mt-6">What we have actually measured.</h2>
            <p className="mt-5 max-w-sm text-muted-foreground">
              Engine figures come from a validation run on an NVIDIA L40S with TensorRT (15 Nov
              2026, earlier model). Quality figures are for the live model, measured on MEAD
              validation clips (17 Nov 2026). Nothing here is a projection.
            </p>
            <Button asChild variant="hairline" className="mt-8">
              <Link to="/research">
                Read the full results <ArrowRight />
              </Link>
            </Button>
          </div>
          <div>
            <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-border bg-border md:grid-cols-3">
              <Stat v="≈25" unit="FPS" k="Frame rate" c={`L40S · TensorRT · ${VALIDATION.date}`} />
              <Stat
                v={String(VALIDATION.serverP50Ms)}
                unit="ms"
                k="Server p50"
                c={`Server-side · ${VALIDATION.date}`}
              />
              <Stat
                v={String(VALIDATION.serverP95Ms)}
                unit="ms"
                k="Server p95"
                c={`Server-side · ${VALIDATION.date}`}
              />
              <Stat
                v={String(VALIDATION.peakVramGiB)}
                unit="GiB"
                k="Peak GPU memory"
                c={`L40S · ${VALIDATION.date}`}
              />
              <Stat
                v={CURRENT.arcface.toFixed(3)}
                k="Identity similarity"
                c={`ArcFace · live model ${CURRENT.model}`}
              />
              <Stat
                v={CURRENT.emotionMacroF1.toFixed(3)}
                k="Emotion macro-F1"
                c={`5 classes · ${CURRENT.model}`}
              />
            </dl>
            <p className="mt-4 border-l-2 border-ember pl-4 text-sm leading-relaxed text-muted-foreground">
              {DISCLAIMER}
            </p>
          </div>
        </div>
      </section>

      {/* RESEARCH IDENTITY */}
      <section className="border-t border-border bg-sunk">
        <div className="mx-auto max-w-[1320px] px-5 py-20 md:px-8 lg:py-24">
          <MotionLine className="text-foreground/25" />
          <div className="mt-12 grid gap-10 lg:grid-cols-[1.2fr_1fr]">
            <blockquote className="font-display text-[clamp(1.75rem,3vw,2.6rem)] leading-[1.12]">
              EmoStream is an academic research project. It asks a narrow question: how cheaply can
              a single portrait be animated from live speech, while keeping the person recognisable
              and the emotion under the user's control?
            </blockquote>
            <div className="space-y-5 text-muted-foreground">
              <p>
                There are no customers, partners or testimonials to show you, and we won't invent
                any. What we can show is the architecture, the measurements, and the limits we know
                about.
              </p>
              <p>
                Every frame EmoStream produces carries a visible AI-generated watermark. Portraits
                are only animated after the uploader confirms they have consent.
              </p>
              <div className="flex flex-wrap gap-3 pt-2">
                <Button asChild variant="ink">
                  <Link to="/app/studio">Give your portrait a voice</Link>
                </Button>
                <Button asChild variant="ghost">
                  <Link to="/about">About the project</Link>
                </Button>
              </div>
            </div>
          </div>
        </div>
      </section>
    </SiteLayout>
  );
}

function HeroFact({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <dt className="eyebrow text-muted-foreground">{k}</dt>
      <dd className="mt-1.5 text-[15px] font-medium">{v}</dd>
    </div>
  );
}

function Stat({ v, unit, k, c }: { v: string; unit?: string; k: string; c: string }) {
  return (
    <div className="bg-surface p-5 md:p-6">
      <dt className="eyebrow text-muted-foreground">{k}</dt>
      <dd className="mt-3 flex items-baseline gap-1">
        <span className="numeral text-[2.6rem] font-medium leading-none">{v}</span>
        {unit && <span className="text-sm text-muted-foreground">{unit}</span>}
      </dd>
      <p className="timecode mt-2 text-[11px] text-muted-foreground">{c}</p>
    </div>
  );
}

function StepGraphic({ i }: { i: number }) {
  const common = "h-10 w-16 text-foreground/60";
  if (i === 0)
    return (
      <svg viewBox="0 0 64 40" className={common} fill="none" aria-hidden>
        <rect x="18" y="2" width="28" height="36" rx="2" className="stroke-current" />
        <circle cx="32" cy="16" r="6" className="stroke-current" />
        <path d="M22 34c2-6 6-8 10-8s8 2 10 8" className="stroke-current" />
      </svg>
    );
  if (i === 1)
    return <WaveformMotif bars={16} seed={3} className={common} barClass="fill-current" />;
  if (i === 2)
    return (
      <ExpressionGlyph emotion="happy" intensity={80} className="h-10 w-14 text-foreground/60" />
    );
  return (
    <svg viewBox="0 0 64 40" className={common} fill="none" aria-hidden>
      {[0, 1, 2].map((k) => (
        <rect
          key={k}
          x={4 + k * 20}
          y="6"
          width="16"
          height="28"
          rx="2"
          className={k === 2 ? "stroke-ember" : "stroke-current"}
        />
      ))}
    </svg>
  );
}
