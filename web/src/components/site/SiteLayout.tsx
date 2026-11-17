import type { ReactNode } from "react";
import { SiteFooter } from "./SiteFooter";
import { SiteHeader } from "./SiteHeader";

export function SiteLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-background">
      <SiteHeader />
      <main className="flex-1">{children}</main>
      <SiteFooter />
    </div>
  );
}

export function SectionLabel({ index, children }: { index?: string; children: ReactNode }) {
  return (
    <p className="eyebrow flex items-center gap-3 text-muted-foreground">
      {index && <span className="text-ember">{index}</span>}
      <span className="h-px w-8 bg-border" />
      {children}
    </p>
  );
}

export function PageIntro({ label, title, children }: { label: string; title: ReactNode; children?: ReactNode }) {
  return (
    <section className="paper-light border-b border-border">
      <div className="mx-auto max-w-[1320px] px-5 pb-14 pt-16 md:px-8 md:pb-20 md:pt-24">
        <SectionLabel>{label}</SectionLabel>
        <h1 className="display-lg mt-6 max-w-4xl text-balance">{title}</h1>
        {children && <div className="mt-6 max-w-2xl text-lg leading-relaxed text-muted-foreground">{children}</div>}
      </div>
    </section>
  );
}
