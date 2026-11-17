import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowRight } from "lucide-react";
import { LogoMark } from "@/components/brand/Logo";
import { WaveformMotif } from "@/components/brand/Waveform";
import { SoonBadge } from "@/components/app/Status";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export const Route = createFileRoute("/sign-in")({
  head: () => ({
    meta: [
      { title: "Sign in — EmoStream" },
      { name: "description", content: "EmoStream's research build has no accounts yet. Open the Studio directly — everything runs in your browser tab." },
      { property: "og:title", content: "Sign in — EmoStream" },
      { property: "og:description", content: "Accounts are planned. Open the Studio directly." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: SignIn,
});

function SignIn() {
  return (
    <div className="grid min-h-screen bg-background lg:grid-cols-2">
      <div className="stage-band grain relative hidden flex-col justify-between p-10 lg:flex">
        <Link to="/" className="relative z-[2] flex items-center gap-2 text-stage-foreground">
          <LogoMark className="size-7" /> <span className="font-semibold">EmoStream</span>
        </Link>
        <div className="relative z-[2]">
          <p className="display-lg text-stage-foreground">One portrait. One voice. A human-like digital presence.</p>
          <WaveformMotif bars={80} seed={31} className="mt-10 h-12 w-full text-stage-foreground/40" />
        </div>
      </div>
      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <Link to="/" className="mb-10 flex items-center gap-2 lg:hidden"><LogoMark className="size-7" /> <span className="font-semibold">EmoStream</span></Link>
          <SoonBadge>Accounts · planned</SoonBadge>
          <h1 className="display-md mt-4">Sign in</h1>
          <p className="mt-3 text-[15px] text-muted-foreground">
            This research build doesn't have accounts. You don't need one: Studio runs in your browser tab, and nothing is saved to a server.
          </p>
          <Button asChild variant="ink" size="lg" className="mt-8 w-full">
            <Link to="/app/studio">Continue to Studio <ArrowRight /></Link>
          </Button>
          <fieldset disabled className="mt-10 space-y-3 opacity-60" aria-label="Sign in (not yet available)">
            <Input type="email" placeholder="Email" aria-label="Email" />
            <Input type="password" placeholder="Password" aria-label="Password" />
            <Button variant="hairline" className="w-full">Sign in</Button>
          </fieldset>
          <p className="mt-3 text-xs text-muted-foreground">Sign-in will open when saved avatars and session history are supported.</p>
        </div>
      </div>
    </div>
  );
}
