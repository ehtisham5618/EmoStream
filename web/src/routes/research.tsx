import { createFileRoute, Link } from "@tanstack/react-router";
import { PipelineDiagram } from "@/components/brand/PipelineDiagram";
import { PageIntro, SectionLabel, SiteLayout } from "@/components/site/SiteLayout";
import { Button } from "@/components/ui/button";
import { CURRENT, DISCLAIMER, HARDWARE, LATENCY_NOTE, MODEL, VALIDATION } from "@/lib/benchmarks";

export const Route = createFileRoute("/research")({
  head: () => ({
    meta: [
      { title: "Research & performance — EmoStream" },
      {
        name: "description",
        content:
          "EmoStream measured results with conditions: ≈25 FPS on L40S with TensorRT, 269/319 ms server p50/p95 and 2.77 GiB peak memory (15 Nov engine run); 0.876 ArcFace, 0.777 emotion macro-F1 and SyncNet 5.08 for the live model.",
      },
      { property: "og:title", content: "EmoStream research & performance" },
      {
        property: "og:description",
        content: "Validated measurements, their conditions, and known limits.",
      },
      { property: "og:type", content: "article" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Research,
});

const FIGS = [
  { v: VALIDATION.resolution, k: "Output resolution", c: "Fixed by the current model" },
  { v: "≈25 FPS", k: "Frame rate", c: `NVIDIA L40S · TensorRT · engine run ${VALIDATION.date}` },
  {
    v: `${VALIDATION.peakVramGiB} GiB`,
    k: "Peak GPU memory",
    c: `L40S · engine run ${VALIDATION.date}`,
  },
  {
    v: `${VALIDATION.serverP50Ms} ms`,
    k: "Server-side p50 latency",
    c: `Excludes network and display · ${VALIDATION.date}, model ${VALIDATION.model}`,
  },
  {
    v: `${VALIDATION.serverP95Ms} ms`,
    k: "Server-side p95 latency",
    c: `Excludes network and display · ${VALIDATION.date}, model ${VALIDATION.model}`,
  },
  {
    v: CURRENT.arcface.toFixed(3),
    k: "Identity similarity",
    c: `ArcFace cosine, source vs output · live model ${CURRENT.model}`,
  },
  {
    v: CURRENT.emotionMacroF1.toFixed(3),
    k: "Emotion macro-F1",
    c: `Five emotion classes · ${CURRENT.model}`,
  },
  {
    v: `${CURRENT.lseC.toFixed(2)} / ${CURRENT.lseD.toFixed(2)}`,
    k: "SyncNet LSE-C / LSE-D",
    c: `Lip sync · ${CURRENT.model}; real video ${CURRENT.realLseC} / ${CURRENT.realLseD}`,
  },
];

const LIMITS = [
  "RTX 4050 performance has not been verified. Consumer GPUs may not reach the L40S frame rate.",
  "Latency figures are server-side. What a viewer experiences also includes network transit, decoding and display.",
  "Output is 512×512. Higher resolutions are not supported by the current model.",
  "Five emotions only, trained on MEAD. Expressions outside that set aren't modelled.",
  "Lip-sync, motion smoothness and boundary-jerk figures aren't published in this build.",
];

function Research() {
  return (
    <SiteLayout>
      <PageIntro
        label="Research & performance"
        title={
          <>
            What we measured, <em className="text-ember">and under what conditions.</em>
          </>
        }
      >
        EmoStream is an academic project investigating efficient, audio-driven, emotion-controllable
        portrait animation. These are the validated figures — nothing projected, nothing rounded up.
      </PageIntro>

      <div className="mx-auto max-w-[1320px] px-5 py-16 md:px-8">
        <dl className="grid gap-px overflow-hidden rounded-xl border border-border bg-border sm:grid-cols-2 lg:grid-cols-4">
          {FIGS.map((f) => (
            <div key={f.k} className="bg-surface p-6">
              <dt className="eyebrow text-muted-foreground">{f.k}</dt>
              <dd className="numeral mt-4 text-[2.4rem] font-medium leading-none">{f.v}</dd>
              <p className="timecode mt-3 text-[11px] text-muted-foreground">{f.c}</p>
            </div>
          ))}
          <div className="bg-sunk p-6 text-sm leading-relaxed text-muted-foreground">
            {LATENCY_NOTE}
          </div>
        </dl>
        <p className="mt-5 max-w-3xl border-l-2 border-ember pl-4 text-[15px] text-muted-foreground">
          {DISCLAIMER}
        </p>

        <section className="mt-20 grid gap-10 lg:grid-cols-[1fr_1.6fr]">
          <div>
            <SectionLabel index="R—01">Hardware</SectionLabel>
            <h2 className="display-md mt-5">Where the numbers come from.</h2>
          </div>
          <ul className="divide-y divide-border border-y border-border">
            {HARDWARE.map((h) => (
              <li key={h.gpu} className="grid gap-2 py-5 sm:grid-cols-[1fr_auto]">
                <div>
                  <p className="text-lg font-medium">{h.gpu}</p>
                  <p className="mt-1 text-sm text-muted-foreground">{h.note}</p>
                </div>
                <p className="timecode self-center text-sm">
                  {h.status === "measured"
                    ? `${h.fps} fps · ${h.vram}`
                    : h.status === "tested"
                      ? "figures pending"
                      : "not yet verified"}
                </p>
              </li>
            ))}
          </ul>
        </section>

        <section className="mt-20 grid gap-10 lg:grid-cols-[1fr_1.6fr]">
          <div>
            <SectionLabel index="R—02">Method</SectionLabel>
            <h2 className="display-md mt-5">A small model, deliberately.</h2>
          </div>
          <div className="space-y-5 text-[15px] leading-relaxed text-muted-foreground">
            <p>
              The research question is efficiency: how little needs to be trained to get
              controllable, real-time animation. {MODEL.name} has {MODEL.params} parameters and is
              causal, so it can stream. It has separate articulation and emotion branches and was
              trained on MEAD.
            </p>
            <p>
              Rendering uses a frozen LivePortrait (Ditto-packaged); speech features come from{" "}
              {MODEL.audioEncoder}. Identity is measured as ArcFace cosine similarity between the
              source portrait and generated frames; emotion as macro-F1 of a classifier on the
              output.
            </p>
            <PipelineDiagram />
          </div>
        </section>

        <section className="mt-20 grid gap-10 lg:grid-cols-[1fr_1.6fr]">
          <div>
            <SectionLabel index="R—03">Limits</SectionLabel>
            <h2 className="display-md mt-5">What we know it can't do yet.</h2>
          </div>
          <ul className="space-y-4">
            {LIMITS.map((l) => (
              <li key={l} className="flex gap-4 text-[15px]">
                <span className="mt-2.5 h-px w-4 shrink-0 bg-ember" />
                {l}
              </li>
            ))}
          </ul>
        </section>

        <div className="mt-20 flex flex-wrap gap-3">
          <Button asChild variant="ink" size="lg">
            <Link to="/app/models">Open Models & Performance</Link>
          </Button>
          <Button asChild variant="hairline" size="lg">
            <Link to="/about">About the project</Link>
          </Button>
        </div>
      </div>
    </SiteLayout>
  );
}
