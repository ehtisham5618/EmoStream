import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  Outlet,
  Link,
  createRootRouteWithContext,
  useRouter,
  HeadContent,
  Scripts,
  type ErrorComponentProps,
} from "@tanstack/react-router";
import { useEffect, type ReactNode } from "react";

import appCss from "../styles.css?url";
import { reportLovableError } from "../lib/lovable-error-reporting";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ThemeSync, themeBootScript } from "@/lib/theme";
import { LogoMark } from "@/components/brand/Logo";

function NotFoundComponent() {
  return (
    <div className="paper-light flex min-h-screen items-center justify-center bg-background px-6">
      <div className="max-w-md text-center">
        <LogoMark className="mx-auto size-10 text-foreground" />
        <p className="eyebrow mt-8 text-muted-foreground">Frame 404 · not found</p>
        <h1 className="display-lg mt-3 text-foreground">This frame is missing.</h1>
        <p className="mt-4 text-sm text-muted-foreground">
          The page you asked for isn't part of EmoStream. It may have moved.
        </p>
        <div className="mt-8 flex justify-center gap-2">
          <Link
            to="/"
            className="inline-flex h-10 items-center rounded-md bg-primary px-5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Back to EmoStream
          </Link>
          <Link
            to="/app/studio"
            className="inline-flex h-10 items-center rounded-md border border-input px-5 text-sm font-medium text-foreground transition-colors hover:bg-accent"
          >
            Open Studio
          </Link>
        </div>
      </div>
    </div>
  );
}

function ErrorComponent({ error, reset }: ErrorComponentProps) {
  console.error(error);
  const router = useRouter();
  useEffect(() => {
    reportLovableError(error, { boundary: "tanstack_root_error_component" });
  }, [error]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <p className="eyebrow text-muted-foreground">Render interrupted</p>
        <h1 className="display-md mt-3 text-foreground">This page didn't load.</h1>
        <p className="mt-3 text-sm text-muted-foreground">
          Something went wrong while drawing this screen. Try again, or head back to the start.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <button
            onClick={() => {
              router.invalidate();
              reset();
            }}
            className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Try again
          </button>
          <a
            href="/"
            className="inline-flex items-center justify-center rounded-md border border-input bg-background px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent"
          >
            Go home
          </a>
        </div>
      </div>
    </div>
  );
}

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { title: "EmoStream — One portrait. One voice." },
      {
        name: "description",
        content:
          "EmoStream turns a single portrait and a live voice into an expressive talking avatar with emotion you control.",
      },
      { name: "author", content: "EmoStream research project" },
      { property: "og:title", content: "EmoStream — One portrait. One voice." },
      {
        property: "og:description",
        content: "Expressive, voice-driven human avatars from a single portrait.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
    links: [
      { rel: "preconnect", href: "https://fonts.googleapis.com" },
      { rel: "preconnect", href: "https://fonts.gstatic.com", crossOrigin: "anonymous" },
      {
        rel: "stylesheet",
        href: "https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Instrument+Serif:ital@0;1&family=Onest:wght@400;500;600;700&display=swap",
      },
      { rel: "stylesheet", href: appCss },
      { rel: "icon", type: "image/svg+xml", href: "/favicon.svg" },
    ],
  }),
  shellComponent: RootShell,
  component: RootComponent,
  notFoundComponent: NotFoundComponent,
  errorComponent: ErrorComponent,
});

function RootShell({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootScript }} />
        <HeadContent />
      </head>
      <body>
        {children}
        <Scripts />
      </body>
    </html>
  );
}

function RootComponent() {
  const { queryClient } = Route.useRouteContext();

  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={250}>
        <ThemeSync />
        <Outlet />
        <Toaster position="bottom-right" />
      </TooltipProvider>
    </QueryClientProvider>
  );
}
