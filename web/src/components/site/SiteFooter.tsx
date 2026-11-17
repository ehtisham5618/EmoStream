import { Link } from "@tanstack/react-router";
import { LogoMark } from "@/components/brand/Logo";
import { MotionLine } from "@/components/brand/MotionLine";

export function SiteFooter() {
  return (
    <footer className="mt-auto border-t border-border bg-sunk">
      <div className="mx-auto max-w-[1320px] px-5 pt-10 md:px-8">
        <MotionLine className="text-border" />
      </div>
      <div className="mx-auto grid max-w-[1320px] gap-10 px-5 py-12 md:grid-cols-[1.4fr_1fr_1fr_1fr] md:px-8">
        <div className="max-w-sm">
          <div className="flex items-center gap-2">
            <LogoMark className="size-7 text-foreground" />
            <span className="font-semibold tracking-tight">EmoStream</span>
          </div>
          <p className="font-display mt-4 text-2xl leading-tight">One portrait. One voice. A human-like digital presence.</p>
          <p className="mt-3 text-sm text-muted-foreground">
            An academic research project on efficient, audio-driven, emotion-controllable portrait animation.
          </p>
        </div>
        <FooterCol
          title="Product"
          links={[
            { to: "/", label: "Product" },
            { to: "/how-it-works", label: "How it works" },
            { to: "/capabilities", label: "Capabilities" },
            { to: "/app/studio", label: "Studio" },
          ]}
        />
        <FooterCol
          title="Research"
          links={[
            { to: "/research", label: "Research & performance" },
            { to: "/app/models", label: "Models" },
            { to: "/app/help", label: "Documentation" },
          ]}
        />
        <FooterCol
          title="Project"
          links={[
            { to: "/about", label: "About" },
            { to: "/privacy", label: "Privacy" },
            { to: "/responsible-ai", label: "Responsible AI" },
            { to: "/about", label: "Contact", hash: "contact" },
          ]}
        />
      </div>
      <div className="border-t border-border">
        <div className="mx-auto flex max-w-[1320px] flex-wrap items-center justify-between gap-3 px-5 py-5 md:px-8">
          <p className="eyebrow text-muted-foreground">EmoStream · research build</p>
          <p className="text-xs text-muted-foreground">Every animated output is labelled as AI-generated.</p>
        </div>
      </div>
    </footer>
  );
}

type FooterLink = { to: "/" | "/how-it-works" | "/capabilities" | "/app/studio" | "/research" | "/app/models" | "/app/help" | "/about" | "/privacy" | "/responsible-ai"; label: string; hash?: string };

function FooterCol({ title, links }: { title: string; links: FooterLink[] }) {
  return (
    <div>
      <p className="eyebrow text-muted-foreground">{title}</p>
      <ul className="mt-4 space-y-2.5">
        {links.map((l) => (
          <li key={l.label}>
            <Link to={l.to} {...(l.hash ? { hash: l.hash } : {})} className="text-sm text-foreground/85 transition-colors hover:text-ember">
              {l.label}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
