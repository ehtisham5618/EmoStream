import { cn } from "@/lib/utils";

/** Profile line that continues into a voice waveform: the face moves with the sound. */
export function LogoMark({ className, accent = true }: { className?: string; accent?: boolean }) {
  return (
    <svg viewBox="0 0 32 32" className={cn("shrink-0", className)} aria-hidden="true" fill="none">
      <g stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
        <path d="M8.5 3.5C11.5 5.3 12.2 8 11.7 10.4L15 13.9L12.4 15.1L13.2 17.3" />
        <path
          d="M13.2 17.3H16.4L18.2 12.6L20.2 22.2L22.2 14.6L24 20.2L25.7 16.2L27 18.4"
          className={accent ? "stroke-ember" : undefined}
        />
        <path d="M13 19.6L12.5 21.3C13.4 22.5 13.6 24.3 11.8 25.3C10.4 26 9.4 27.3 9.4 29" />
      </g>
    </svg>
  );
}

export function Wordmark({
  className,
  compact = false,
}: {
  className?: string;
  compact?: boolean;
}) {
  return (
    <span className={cn("inline-flex items-center gap-2 text-foreground", className)}>
      <LogoMark className="size-7" />
      {!compact && (
        <span className="text-[1.15rem] font-semibold tracking-[-0.03em]">
          Emo
          <span className="font-display text-[1.35rem] font-normal italic tracking-[-0.01em]">
            Stream
          </span>
        </span>
      )}
    </span>
  );
}
