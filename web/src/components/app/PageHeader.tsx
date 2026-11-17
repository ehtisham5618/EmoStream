import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function PageHeader({
  label,
  title,
  description,
  actions,
  className,
}: {
  label: string;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <header
      className={cn(
        "flex flex-wrap items-end justify-between gap-6 border-b border-border pb-7",
        className,
      )}
    >
      <div className="max-w-2xl">
        <p className="eyebrow text-muted-foreground">{label}</p>
        <h1 className="display-md mt-3">{title}</h1>
        {description && (
          <p className="mt-3 text-[15px] leading-relaxed text-muted-foreground">{description}</p>
        )}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

export function Page({
  children,
  className,
  wide = false,
}: {
  children: ReactNode;
  className?: string;
  wide?: boolean;
}) {
  return (
    <div
      className={cn(
        "mx-auto w-full px-5 py-8 md:px-8 md:py-10",
        wide ? "max-w-[1480px]" : "max-w-[1200px]",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function SectionTitle({
  label,
  title,
  aside,
}: {
  label?: string;
  title: ReactNode;
  aside?: ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        {label && <p className="eyebrow text-muted-foreground">{label}</p>}
        <h2 className="heading mt-1.5 text-[1.2rem]">{title}</h2>
      </div>
      {aside}
    </div>
  );
}
