import { Link } from "@tanstack/react-router";
import { Menu, X } from "lucide-react";
import { useState } from "react";
import { Wordmark } from "@/components/brand/Logo";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Product" },
  { to: "/how-it-works", label: "How it works" },
  { to: "/capabilities", label: "Capabilities" },
  { to: "/research", label: "Research & performance" },
  { to: "/about", label: "About" },
] as const;

export function SiteHeader() {
  const [open, setOpen] = useState(false);
  return (
    <header className="sticky top-0 z-40 border-b border-border/70 bg-background/85 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-[1320px] items-center gap-8 px-5 md:px-8">
        <Link to="/" aria-label="EmoStream home">
          <Wordmark />
        </Link>
        <nav className="hidden items-center gap-1 lg:flex" aria-label="Primary">
          {NAV.map((n) => (
            <Link
              key={n.to}
              to={n.to}
              activeOptions={{ exact: true }}
              className="relative rounded-md px-3 py-2 text-[13.5px] text-muted-foreground transition-colors hover:text-foreground data-[status=active]:text-foreground data-[status=active]:after:absolute data-[status=active]:after:inset-x-3 data-[status=active]:after:-bottom-[13px] data-[status=active]:after:h-px data-[status=active]:after:bg-ember"
            >
              {n.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto hidden items-center gap-2 lg:flex">
          <Button asChild variant="ghost" size="sm">
            <Link to="/sign-in">Sign in</Link>
          </Button>
          <Button asChild variant="ink" size="sm">
            <Link to="/app/studio">Open Studio</Link>
          </Button>
        </div>
        <button
          className="ml-auto inline-flex size-10 items-center justify-center rounded-md hover:bg-accent lg:hidden"
          onClick={() => setOpen((o) => !o)}
          aria-label={open ? "Close menu" : "Open menu"}
          aria-expanded={open}
        >
          {open ? <X className="size-5" /> : <Menu className="size-5" />}
        </button>
      </div>
      <div className={cn("grid overflow-hidden transition-[grid-template-rows] duration-300 ease-soft lg:hidden", open ? "grid-rows-[1fr]" : "grid-rows-[0fr]")}>
        <nav className="min-h-0 px-5 pb-0" aria-label="Mobile">
          <div className="flex flex-col gap-1 border-t border-border py-4">
            {NAV.map((n) => (
              <Link key={n.to} to={n.to} onClick={() => setOpen(false)} className="rounded-md px-2 py-2.5 text-[15px] hover:bg-accent">
                {n.label}
              </Link>
            ))}
            <div className="mt-3 flex gap-2">
              <Button asChild variant="outline" className="flex-1">
                <Link to="/sign-in">Sign in</Link>
              </Button>
              <Button asChild variant="ink" className="flex-1">
                <Link to="/app/studio">Open Studio</Link>
              </Button>
            </div>
          </div>
        </nav>
      </div>
    </header>
  );
}
