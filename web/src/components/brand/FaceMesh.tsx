import { faceLandmarks, smoothPath, toPath, type Pt } from "@/lib/face-geometry";
import type { FaceParams } from "@/lib/emotions";
import { cn } from "@/lib/utils";

interface Props {
  params: FaceParams;
  className?: string | undefined;
  /** "full" = head, jaw, shoulders. "features" = brows, eyes, mouth only (for glyphs). */
  variant?: "full" | "features";
  dots?: boolean;
  /** Tailwind stroke/fill colour classes */
  lineClass?: string;
  dotClass?: string;
  accentClass?: string;
}

export function FaceMesh({
  params,
  className,
  variant = "full",
  dots = true,
  lineClass = "stroke-current",
  dotClass = "fill-current",
  accentClass = "stroke-ember",
}: Props) {
  const f = faceLandmarks(params);
  const allFeature: Pt[] = [
    ...f.browL,
    ...f.browR,
    ...f.eyeL.upper,
    ...f.eyeL.lower.slice(1, -1),
    ...f.eyeR.upper,
    ...f.eyeR.lower.slice(1, -1),
    ...f.outerUpper,
    ...f.outerLower.slice(1, -1),
  ];
  const viewBox = variant === "features" ? "150 140 212 240" : "0 0 512 512";

  return (
    <svg
      viewBox={viewBox}
      className={cn("overflow-visible", className)}
      aria-hidden="true"
      fill="none"
    >
      {variant === "full" && (
        <g className={lineClass} strokeWidth="1" opacity="0.35">
          {/* cranium + hairline */}
          <path d="M138 222 C 128 120, 196 62, 256 62 C 316 62, 384 120, 374 222" />
          <path
            d="M160 168 C 190 118, 236 104, 300 116 C 334 124, 356 146, 362 172"
            strokeDasharray="2 5"
          />
          {/* neck + shoulders */}
          <path d="M210 398 C 212 430, 206 452, 176 466 C 132 480, 92 492, 60 512" />
          <path d="M302 398 C 300 430, 306 452, 336 466 C 380 480, 420 492, 452 512" />
          {/* ears */}
          <path d="M140 214 C 124 212, 120 236, 126 256 C 130 272, 140 280, 146 282" />
          <path d="M372 214 C 388 212, 392 236, 386 256 C 382 272, 372 280, 366 282" />
        </g>
      )}
      <g
        className={lineClass}
        strokeWidth={variant === "features" ? 3.4 : 1.25}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {variant === "full" && <path d={smoothPath(f.jaw)} opacity="0.8" />}
        <path d={smoothPath(f.browL)} />
        <path d={smoothPath(f.browR)} />
        <path d={smoothPath(f.eyeL.upper)} />
        <path d={smoothPath(f.eyeL.lower)} opacity="0.6" />
        <path d={smoothPath(f.eyeR.upper)} />
        <path d={smoothPath(f.eyeR.lower)} opacity="0.6" />
        {variant === "full" && (
          <>
            <path d={toPath(f.noseBridge)} opacity="0.6" />
            <path d={smoothPath(f.noseBase)} opacity="0.8" />
          </>
        )}
      </g>
      <g
        className={accentClass}
        strokeWidth={variant === "features" ? 3.6 : 1.6}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d={smoothPath(f.outerUpper)} />
        <path d={smoothPath(f.outerLower)} />
        <path d={smoothPath(f.innerUpper)} opacity="0.7" />
        <path d={smoothPath(f.innerLower)} opacity="0.7" />
      </g>
      {variant === "full" && (
        <g className={dotClass} opacity="0.9">
          <circle cx={f.eyeL.pupil[0]} cy={f.eyeL.pupil[1]} r="3.4" />
          <circle cx={f.eyeR.pupil[0]} cy={f.eyeR.pupil[1]} r="3.4" />
        </g>
      )}
      {dots && (
        <g className={dotClass}>
          {(variant === "full"
            ? [...f.jaw, ...f.noseBridge, ...f.noseBase, ...allFeature]
            : allFeature
          ).map(([x, y], i) => (
            <circle key={i} cx={x} cy={y} r={variant === "features" ? 2.6 : 1.9} />
          ))}
        </g>
      )}
    </svg>
  );
}
