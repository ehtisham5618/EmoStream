import { createFileRoute, Link } from "@tanstack/react-router";
import { MotionLine } from "@/components/brand/MotionLine";
import { PageIntro, SectionLabel, SiteLayout } from "@/components/site/SiteLayout";
import { Button } from "@/components/ui/button";

export const Route = createFileRoute("/about")({
  head: () => ({
    meta: [
      { title: "About — EmoStream" },
      { name: "description", content: "EmoStream is an academic research project on efficient, audio-driven, emotion-controllable portrait animation." },
      { property: "og:title", content: "About EmoStream" },
      { property: "og:description", content: "An academic research project on voice-driven, emotion-controllable portrait animation." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: About,
});

function About() {
  return (
    <SiteLayout>
      <PageIntro label="About" title={<>A research project, <em className="text-ember">said plainly.</em></>}>
        EmoStream studies how to animate a single portrait from live speech — cheaply enough to stream, faithfully enough to stay recognisable, and with emotion the user controls.
      </PageIntro>
      <div className="mx-auto max-w-[1320px] space-y-20 px-5 py-16 md:px-8">
        <section className="grid gap-10 lg:grid-cols-[1fr_1.6fr]">
          <div>
            <SectionLabel index="A—01">Why it exists</SectionLabel>
            <h2 className="display-md mt-5">Most talking-head systems are heavy. This one tries not to be.</h2>
          </div>
          <div className="space-y-4 text-[15px] leading-relaxed text-muted-foreground">
            <p>High-quality portrait animation usually means large models and offline rendering. EmoStream asks whether a 1.3M-parameter causal model, sitting between a pretrained audio encoder and a frozen renderer, can drive a believable, controllable face in real time.</p>
            <p>The answer so far: about 25 frames per second on an L40S, with strong identity preservation and measurable emotion control — and clear limits we publish alongside.</p>
          </div>
        </section>

        <section className="grid gap-10 lg:grid-cols-[1fr_1.6fr]">
          <div>
            <SectionLabel index="A—02">What we won't do</SectionLabel>
            <h2 className="display-md mt-5">No invented proof.</h2>
          </div>
          <ul className="space-y-3 text-[15px]">
            {["No testimonials, client logos or user counts — there are no customers.", "No numbers that weren't measured.", "No animation of a portrait without the uploader's consent.", "No output without an AI-generated label."].map((t) => (
              <li key={t} className="flex gap-4"><span className="mt-2.5 h-px w-4 shrink-0 bg-ember" />{t}</li>
            ))}
          </ul>
        </section>

        <MotionLine className="text-border" />

        <section id="contact" className="scroll-mt-24 grid gap-10 lg:grid-cols-[1fr_1.6fr]">
          <div>
            <SectionLabel index="A—03">Contact</SectionLabel>
            <h2 className="display-md mt-5">Get in touch.</h2>
          </div>
          <div className="space-y-4 text-[15px] leading-relaxed text-muted-foreground">
            <p>Contact details for the research team will be published with the project release. Until then, the most useful place to start is the documentation inside the app.</p>
            <div className="flex flex-wrap gap-3 pt-2">
              <Button asChild variant="ink"><Link to="/app/help">Read the documentation</Link></Button>
              <Button asChild variant="hairline"><Link to="/research">Research & performance</Link></Button>
            </div>
          </div>
        </section>
      </div>
    </SiteLayout>
  );
}
