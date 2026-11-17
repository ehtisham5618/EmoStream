import { cn } from "@/lib/utils";

/** The continuous face-motion line: a profile that resolves into speech. Used as a section divider. */
export function MotionLine({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 1200 60" preserveAspectRatio="none" className={cn("block h-10 w-full", className)} aria-hidden="true" fill="none">
      <path
        d="M0 30 H420 C 440 30, 446 12, 458 12 C 470 12, 472 26, 482 26 L 494 30 L 486 36 C 490 42, 498 44, 504 44 H 560 L 572 18 L 586 46 L 600 14 L 614 42 L 628 22 L 640 38 L 652 28 L 664 34 L 676 30 H1200"
        className="stroke-current"
        strokeWidth="1.25"
        vectorEffect="non-scaling-stroke"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}
