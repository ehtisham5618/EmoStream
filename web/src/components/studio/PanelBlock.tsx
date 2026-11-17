import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function PanelBlock({
  index,
  title,
  hint,
  children,
  className,
}: {
  index: string;
  title: string;
  hint?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("panel p-4", className)} aria-label={title}>
      <header className="mb-3 flex items-center justify-between">
        <h2 className="flex items-baseline gap-2">
          <span className="timecode text-[11px] text-ember">{index}</span>
          <span className="text-[13.5px] font-semibold">{title}</span>
        </h2>
        {hint && <span className="timecode text-[10.5px] text-muted-foreground">{hint}</span>}
      </header>
      {children}
    </section>
  );
}
