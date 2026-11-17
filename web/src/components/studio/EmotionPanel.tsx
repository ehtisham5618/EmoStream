import { ExpressionGlyph } from "@/components/brand/ExpressionGlyph";
import { Slider } from "@/components/ui/slider";
import { EMOTIONS, emotionById } from "@/lib/emotions";
import { studioStore, useStudio } from "@/lib/studio-store";
import { cn } from "@/lib/utils";
import { PanelBlock } from "./PanelBlock";

export function EmotionPanel({ live }: { live: boolean }) {
  const emotion = useStudio((s) => s.emotion);
  const intensity = useStudio((s) => s.intensity);
  const current = emotionById(emotion);

  return (
    <PanelBlock index="03" title="Expression" hint={live ? <span className="text-live">● live</span> : undefined}>
      <p className="font-display text-[1.35rem] leading-tight">Choose how your avatar expresses itself.</p>

      <div className="mt-4 grid grid-cols-5 gap-1.5" role="radiogroup" aria-label="Emotion">
        {EMOTIONS.map((e) => {
          const on = e.id === emotion;
          return (
            <button
              key={e.id}
              role="radio"
              aria-checked={on}
              onClick={() => studioStore.set({ emotion: e.id })}
              className={cn(
                "group relative flex flex-col items-center rounded-md border px-0.5 pb-1.5 pt-2 transition-[border-color,background-color,transform] duration-200 ease-soft",
                on ? cn("bg-surface shadow-sm", e.borderClass) : "border-transparent bg-sunk hover:border-border hover:bg-surface",
              )}
            >
              <ExpressionGlyph
                emotion={e.id}
                intensity={on ? Math.max(intensity, 35) : 85}
                className={cn("h-10 w-full transition-opacity", on ? "text-foreground" : "text-foreground/45 group-hover:text-foreground/70")}
                accentClass={on ? "stroke-ember" : "stroke-current"}
              />
              <span className={cn("mt-1 text-[10.5px]", on ? "font-semibold" : "text-muted-foreground")}>{e.label}</span>
              <span className={cn("absolute inset-x-3 -bottom-px h-[2px] rounded-full transition-opacity", e.bgClass, on ? "opacity-100" : "opacity-0")} />
            </button>
          );
        })}
      </div>

      {/* blended preview */}
      <div className="mt-4 grid grid-cols-[96px_1fr] items-center gap-4 rounded-md border border-border bg-sunk p-3">
        <div className="stage aspect-square rounded-md p-2">
          <ExpressionGlyph emotion={emotion} intensity={intensity} className="h-full w-full text-stage-foreground/85" />
        </div>
        <div>
          <p className="eyebrow text-[10px] text-muted-foreground">Intensity</p>
          <p className="mt-1 flex items-baseline gap-1">
            <span className="numeral text-[2.75rem] font-medium leading-none" aria-live="polite">
              {intensity}
            </span>
            <span className="text-sm text-muted-foreground">%</span>
          </p>
          <p className={cn("mt-1 text-xs font-medium", current.colorClass)}>{current.label}</p>
        </div>
      </div>

      <div className="mt-4">
        <Slider
          value={[intensity]}
          min={0}
          max={100}
          step={1}
          onValueChange={([v]) => studioStore.set({ intensity: v ?? 0 })}
          aria-label="Emotion intensity"
        />
        <div className="timecode mt-2 flex justify-between text-[10px] text-muted-foreground">
          <span>0 · subtle</span>
          <span>50</span>
          <span>100 · full</span>
        </div>
      </div>

      <p className="mt-4 border-l-2 border-ember pl-3 text-xs leading-relaxed text-muted-foreground">
        Voice controls articulation. Your selected emotion controls expression.
        {live && " Changes apply to the next frames — no need to stop."}
      </p>
    </PanelBlock>
  );
}
