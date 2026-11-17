import { faceFor, type EmotionId } from "@/lib/emotions";
import { FaceMesh } from "./FaceMesh";

/** Landmark-style expression diagram: brows, eyes and mouth blended by intensity. */
export function ExpressionGlyph({
  emotion,
  intensity = 100,
  className,
  accentClass = "stroke-ember",
}: {
  emotion: EmotionId;
  intensity?: number;
  className?: string;
  accentClass?: string;
}) {
  return (
    <FaceMesh
      params={faceFor(emotion, intensity)}
      variant="features"
      className={className}
      dots={false}
      accentClass={accentClass}
    />
  );
}
