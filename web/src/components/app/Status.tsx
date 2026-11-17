import { cva, type VariantProps } from "class-variance-authority";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

const pill = cva(
  "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-[3px] font-mono text-[10.5px] font-medium uppercase tracking-[0.08em]",
  {
    variants: {
      tone: {
        live: "border-live/30 bg-live/10 text-live",
        success: "border-success/30 bg-success/10 text-success",
        warning: "border-warning/40 bg-warning/10 text-foreground",
        soon: "border-dashed border-soon/60 bg-transparent text-soon",
        muted: "border-border bg-muted/60 text-muted-foreground",
        demo: "border-ember/35 bg-ember/8 text-ember",
        stage: "border-stage-line bg-stage-raised/80 text-stage-foreground",
      },
    },
    defaultVariants: { tone: "muted" },
  },
);

export function StatusPill({
  tone,
  children,
  dot = false,
  pulse = false,
  className,
}: VariantProps<typeof pill> & { children: ReactNode; dot?: boolean; pulse?: boolean; className?: string | undefined }) {
  return (
    <span className={cn(pill({ tone }), className)}>
      {dot && <span className={cn("size-1.5 rounded-full bg-current", pulse && "animate-rec")} />}
      {children}
    </span>
  );
}

export function DemoNote({ children = "Demonstration data", className }: { children?: ReactNode; className?: string | undefined }) {
  return (
    <StatusPill tone="demo" className={className}>
      {children}
    </StatusPill>
  );
}

export function SoonBadge({ children = "Coming soon" }: { children?: ReactNode }) {
  return <StatusPill tone="soon">{children}</StatusPill>;
}
