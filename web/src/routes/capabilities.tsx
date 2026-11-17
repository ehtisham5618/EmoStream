import { createFileRoute, Link } from "@tanstack/react-router";
import { ExpressionGlyph } from "@/components/brand/ExpressionGlyph";
import { FaceMesh } from "@/components/brand/FaceMesh";
import { WaveformMotif } from "@/components/brand/Waveform";
import { PageIntro, SiteLayout } from "@/components/site/SiteLayout";
import { Button } from "@/components/ui/button";
import { faceFor, NEUTRAL_FACE } from "@/lib/emotions";

export const Route = createFileRoute("/capabilities")({
  head: () => ({
    meta: [
      { title: "Capabilities — EmoStream" },
      { name: "description", content: "Lip sync, jaw articulation, eye and brow expression, head motion, five emotions, continuous streaming and identity preservation." },
      { property: "og:title", content: "What EmoStream can do" },
      { property: "og:description", content: "Every capability of EmoStream's audio-driven portrait animation." },
      { property: "og:type", content: "article" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Capabilities,
});

const CAPS: { title: string; body: string; viz: React.ReactNode }[] = [
  { title: "Audio-driven lip synchronisation", body: "Lip shapes follow the sounds you make, frame by frame, from the audio alone.", viz: <MouthPair a={0.1} b={0.7} /> },
  { title: "Natural jaw articulation", body: "The jaw opens and closes with syllables, so speech reads as physical rather than pasted on.", viz: <MouthPair a={0} b={0.9} jaw /> },
  { title: "Facial movement", body: "Cheeks and surrounding features move with the mouth instead of staying frozen.", viz: <FaceMesh params={faceFor("happy", 50, { mouthOpen: 0.3 })} className="h-28 w-28 text-foreground/70" /> },
  { title: "Eye and eyebrow expression", body: "Brows lift, knit and soften; eyes widen or narrow with the chosen emotion.", viz: <div className="flex gap-3"><ExpressionGlyph emotion="surprised" className="h-20 w-20 text-foreground/70" /><ExpressionGlyph emotion="angry" className="h-20 w-20 text-foreground/70" /></div> },
  { title: "Head movement", body: "Small, speech-linked head motion keeps the portrait from looking pinned in place.", viz: <HeadArc /> },
  { title: "Emotion selection", body: "Neutral, happy, sad, angry or surprised, at any intensity from 0 to 100%.", viz: <div className="flex gap-1">{(["neutral", "happy", "sad", "angry", "surprised"] as const).map((e) => <ExpressionGlyph key={e} emotion={e} className="h-14 w-11 text-foreground/70" />)}</div> },
  { title: "Continuous animation", body: "A causal model streams motion as you speak, with no need to finish a sentence first.", viz: <WaveformMotif bars={60} seed={21} className="h-12 w-48 text-foreground/60" /> },
  { title: "Identity preservation", body: "The person stays recognisable while they speak — 0.930 ArcFace similarity in validation.", viz: <div className="text-center"><span className="numeral text-5xl font-medium">0.930</span><p className="timecode mt-1 text-[10px] text-muted-foreground">ArcFace cosine · validation</p></div> },
];

function Capabilities() {
  return (
    <SiteLayout>
      <PageIntro label="Capabilities" title={<>Eight things the face does <em className="text-ember">while you talk.</em></>}>
        Everything below runs from one portrait and one audio stream. The diagrams are drawn to explain the behaviour; they aren't rendered output.
      </PageIntro>
      <div className="mx-auto max-w-[1320px] px-5 py-16 md:px-8">
        <ul className="grid gap-px overflow-hidden rounded-xl border border-border bg-border md:grid-cols-2">
          {CAPS.map((c, i) => (
            <li key={c.title} className="grid grid-cols-[1fr_auto] items-center gap-6 bg-surface p-7 md:p-9">
              <div>
                <span className="timecode text-xs text-ember">{String(i + 1).padStart(2, "0")}</span>
                <h2 className="font-display mt-3 text-[1.9rem] leading-tight">{c.title}</h2>
                <p className="mt-3 max-w-sm text-muted-foreground">{c.body}</p>
              </div>
              <div className="flex min-w-[120px] justify-center">{c.viz}</div>
            </li>
          ))}
        </ul>
        <div className="mt-12 flex flex-wrap gap-3">
          <Button asChild variant="ink" size="lg"><Link to="/app/studio">Try it in Studio</Link></Button>
          <Button asChild variant="hairline" size="lg"><Link to="/research">See the measurements</Link></Button>
        </div>
      </div>
    </SiteLayout>
  );
}

function MouthPair({ a, b, jaw }: { a: number; b: number; jaw?: boolean }) {
  return (
    <div className="flex gap-2">
      {[a, b].map((m, i) => (
        <div key={i} className="text-center">
          <FaceMesh params={{ ...NEUTRAL_FACE, mouthOpen: m }} variant={jaw ? "full" : "features"} dots={false} className="h-24 w-20 text-foreground/70" />
          <span className="timecode text-[9px] text-muted-foreground">F{i === 0 ? "0120" : "0123"}</span>
        </div>
      ))}
    </div>
  );
}

function HeadArc() {
  return (
    <svg viewBox="0 0 120 90" className="h-24 w-32 text-foreground/70" fill="none" aria-hidden>
      {[-14, 0, 14].map((r, i) => (
        <g key={r} transform={`rotate(${r} 60 80)`} opacity={i === 1 ? 1 : 0.35}>
          <ellipse cx="60" cy="38" rx="18" ry="24" className="stroke-current" strokeWidth="1.2" />
        </g>
      ))}
      <path d="M30 14 Q60 2 90 14" className="stroke-ember" strokeDasharray="2 3" />
    </svg>
  );
}
