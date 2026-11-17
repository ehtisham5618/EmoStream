import { createFileRoute } from "@tanstack/react-router";
import { PageIntro, SiteLayout } from "@/components/site/SiteLayout";

export const Route = createFileRoute("/responsible-ai")({
  head: () => ({
    meta: [
      { title: "Responsible AI — EmoStream" },
      {
        name: "description",
        content:
          "Consent before animation, a permanent AI-generated watermark, and honest limits: how EmoStream approaches responsible use.",
      },
      { property: "og:title", content: "Responsible AI — EmoStream" },
      {
        property: "og:description",
        content: "Consent, disclosure and honest limits in EmoStream.",
      },
      { property: "og:type", content: "article" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: Responsible,
});

const RULES: [string, string][] = [
  [
    "Consent first",
    "Studio won't start a session until you confirm you have the right to use the portrait and the person has agreed to it being animated.",
  ],
  [
    "Always disclosed",
    "Every preview frame carries an “AI-generated · EmoStream” watermark. There's no setting to remove it.",
  ],
  [
    "No impersonation",
    "Don't use EmoStream to make someone appear to say things they didn't, to deceive viewers, or to present output as real footage.",
  ],
  [
    "Minimal retention",
    "Portraits live in your browser tab. Nothing is stored on a server by this interface.",
  ],
  [
    "Honest claims",
    "We publish only measured figures, with their conditions and known limits. Untested hardware is labelled as such.",
  ],
];

function Responsible() {
  return (
    <SiteLayout>
      <PageIntro label="Responsible AI" title="A convincing face needs firm rules.">
        Animated portraits can mislead. These are the rules built into EmoStream, and the ones we
        ask you to follow.
      </PageIntro>
      <ol className="mx-auto max-w-[900px] px-5 py-12 md:px-8">
        {RULES.map(([k, v], i) => (
          <li
            key={k}
            className="grid gap-2 border-b border-border py-7 md:grid-cols-[60px_200px_1fr]"
          >
            <span className="timecode text-sm text-ember">0{i + 1}</span>
            <h2 className="font-display text-2xl">{k}</h2>
            <p className="text-[15px] leading-relaxed text-muted-foreground">{v}</p>
          </li>
        ))}
      </ol>
    </SiteLayout>
  );
}
