import { faceFor, type EmotionId } from "@/lib/emotions";
import { speechEnvelope } from "@/lib/face-geometry";
import { cn } from "@/lib/utils";
import { FaceMesh } from "./FaceMesh";

/** Film-strip of mouth/jaw states: shows how audio frames become articulation. Illustration. */
export function FrameStrip({
  frames = 6,
  start = 112,
  emotion = "neutral",
  intensity = 0,
  className,
}: {
  frames?: number;
  start?: number;
  emotion?: EmotionId;
  intensity?: number;
  className?: string;
}) {
  return (
    <div className={cn("grid gap-1.5", className)} style={{ gridTemplateColumns: `repeat(${frames}, minmax(0, 1fr))` }}>
      {Array.from({ length: frames }, (_, i) => {
        const open = Math.min(1, 0.1 + speechEnvelope((start + i * 3) * 0.07) * 1.1);
        return (
          <figure key={i} className="overflow-hidden rounded-[3px] border border-stage-line bg-stage-raised">
            <FaceMesh
              params={faceFor(emotion, intensity, { mouthOpen: open })}
              variant="features"
              dots={false}
              className="aspect-[212/240] w-full p-1 text-stage-foreground/70"
            />
            <figcaption className="timecode border-t border-stage-line px-1.5 py-1 text-[9px] text-stage-muted">
              F{String(start + i * 3).padStart(4, "0")}
            </figcaption>
          </figure>
        );
      })}
    </div>
  );
}
