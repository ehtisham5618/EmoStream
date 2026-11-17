import { createFileRoute } from "@tanstack/react-router";
import { PageIntro, SiteLayout } from "@/components/site/SiteLayout";

export const Route = createFileRoute("/privacy")({
  head: () => ({
    meta: [
      { title: "Privacy — EmoStream" },
      {
        name: "description",
        content:
          "What EmoStream's interface does with your portrait and voice: kept in your browser tab, sent only to an engine you connect.",
      },
      { property: "og:title", content: "Privacy — EmoStream" },
      { property: "og:description", content: "How EmoStream handles portraits and audio." },
      { property: "og:type", content: "article" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: Privacy,
});

const ITEMS: [string, string][] = [
  [
    "Your portrait",
    "Read in your browser and kept in this tab's memory. It's sent — as a 512×512 crop — only to an engine address you enter, and only when you start a session. Closing the tab discards it.",
  ],
  [
    "Your voice",
    "Captured only after your browser asks and you allow it, and only while a session runs. Audio is streamed to the connected engine; this interface doesn't record or store it.",
  ],
  [
    "Settings",
    "Theme, defaults and the engine address are saved in your browser's local storage. Clear them any time from Settings.",
  ],
  [
    "The engine",
    "What a connected engine keeps depends on how it's deployed. The current research engine does not persist sessions.",
  ],
  [
    "Accounts and analytics",
    "There are no accounts. This interface doesn't add tracking of its own.",
  ],
];

function Privacy() {
  return (
    <SiteLayout>
      <PageIntro label="Privacy" title="What happens to your face and voice.">
        Short version: they stay in your browser unless you connect an engine and start a session.
      </PageIntro>
      <dl className="mx-auto max-w-[900px] divide-y divide-border px-5 py-12 md:px-8">
        {ITEMS.map(([k, v]) => (
          <div key={k} className="grid gap-2 py-6 md:grid-cols-[200px_1fr]">
            <dt className="font-display text-2xl">{k}</dt>
            <dd className="text-[15px] leading-relaxed text-muted-foreground">{v}</dd>
          </div>
        ))}
      </dl>
    </SiteLayout>
  );
}
