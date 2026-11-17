import { cn } from "@/lib/utils";

interface Node {
  id: string;
  title: string;
  sub: string;
  tone?: "input" | "model" | "frozen" | "output";
}

const ROWS: [[Node, Node], [Node, Node, Node]] = [
  [
    { id: "portrait", title: "Portrait", sub: "single image", tone: "input" },
    { id: "appearance", title: "Appearance representation", sub: "built once per avatar", tone: "frozen" },
  ],
  [
    { id: "voice", title: "Voice", sub: "16 kHz stream", tone: "input" },
    { id: "hubert", title: "HuBERT", sub: "speech features", tone: "frozen" },
    { id: "bnet", title: "BehaviourNet", sub: "1.36M · causal", tone: "model" },
  ],
];

const toneCls: Record<NonNullable<Node["tone"]>, string> = {
  input: "border-foreground/25 bg-surface",
  model: "border-ember bg-ember/8",
  frozen: "border-border bg-sunk",
  output: "border-primary bg-primary text-primary-foreground",
};

function Box({ n, className }: { n: Node; className?: string }) {
  return (
    <div className={cn("rounded-md border px-3 py-2.5", toneCls[n.tone ?? "frozen"], className)}>
      <p className="text-[13px] font-semibold leading-tight">{n.title}</p>
      <p className={cn("timecode mt-0.5 text-[10px]", n.tone === "output" ? "text-primary-foreground/75" : "text-muted-foreground")}>{n.sub}</p>
    </div>
  );
}

const Arrow = ({ className }: { className?: string }) => (
  <span className={cn("relative mx-1 hidden h-px min-w-5 flex-1 bg-foreground/30 md:block", className)} aria-hidden>
    <span className="absolute -right-px -top-[3px] size-[7px] rotate-45 border-r border-t border-foreground/40" />
  </span>
);

/** Portrait → appearance; Voice → HuBERT → BehaviourNet → articulation + emotion; fusion → LivePortrait → stream. */
export function PipelineDiagram({ className }: { className?: string }) {
  return (
    <div className={cn("rounded-xl border border-border bg-surface p-5 md:p-7", className)} role="img" aria-label="EmoStream architecture: portrait to appearance representation; voice to HuBERT to BehaviourNet, which outputs articulation and emotion; motion fusion feeds the LivePortrait renderer, which outputs a video stream.">
      <div className="grid gap-4 md:grid-cols-[minmax(0,1.7fr)_auto_minmax(0,1fr)_auto_minmax(0,1fr)] md:items-center">
        <div className="space-y-4">
          <div className="flex flex-col gap-2 md:flex-row md:items-center">
            <Box n={ROWS[0][0]} className="md:w-32" />
            <Arrow />
            <Box n={ROWS[0][1]} className="md:flex-[2]" />
          </div>
          <div className="flex flex-col gap-2 md:flex-row md:items-center">
            <Box n={ROWS[1][0]} className="md:w-32" />
            <Arrow />
            <Box n={ROWS[1][1]} />
            <Arrow />
            <div className="space-y-1.5">
              <Box n={ROWS[1][2]} />
              <div className="flex flex-wrap gap-1.5">
                <span className="timecode rounded-[3px] border border-ember/40 flex-1 px-1.5 py-1 text-center text-[9.5px] text-ember">articulation</span>
                <span className="timecode rounded-[3px] border border-ember/40 flex-1 px-1.5 py-1 text-center text-[9.5px] text-ember">emotion</span>
              </div>
            </div>
          </div>
          <p className="timecode text-[10px] text-muted-foreground">+ emotion label & intensity from the user → emotion branch</p>
        </div>
        <Arrow className="md:max-w-10" />
        <Box n={{ id: "fusion", title: "Motion fusion", sub: "appearance + motion", tone: "model" }} />
        <Arrow className="md:max-w-10" />
        <div className="space-y-2">
          <Box n={{ id: "lp", title: "LivePortrait renderer", sub: "frozen · Ditto-packaged", tone: "frozen" }} />
          <Box n={{ id: "out", title: "Video stream", sub: "512×512 · watermarked", tone: "output" }} />
        </div>
      </div>
      <div className="mt-5 flex flex-wrap gap-4 border-t border-border pt-4 text-[11px] text-muted-foreground">
        <Legend cls="border-foreground/25 bg-surface" t="Input" />
        <Legend cls="border-ember bg-ember/8" t="Trained by EmoStream" />
        <Legend cls="border-border bg-sunk" t="Frozen / pretrained" />
        <Legend cls="border-primary bg-primary" t="Output" />
      </div>
    </div>
  );
}

const Legend = ({ cls, t }: { cls: string; t: string }) => (
  <span className="flex items-center gap-1.5">
    <span className={cn("size-3 rounded-[2px] border", cls)} /> {t}
  </span>
);
