import { createFileRoute } from "@tanstack/react-router";
import { Play, Sparkles, Wand2 } from "lucide-react";
import { useState } from "react";
import { Page, PageHeader } from "@/components/app/PageHeader";
import { SoonBadge } from "@/components/app/Status";
import { useComingSoon } from "@/components/app/ComingSoon";
import { WaveformMotif } from "@/components/brand/Waveform";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/app/text-to-speech")({
  head: () => ({
    meta: [
      { title: "Text to speech — EmoStream (coming soon)" },
      { name: "description", content: "Type what your avatar should say. Text → TTS → audio → EmoStream animation. Coming soon." },
      { property: "og:title", content: "Text to speech — EmoStream" },
      { property: "og:description", content: "Type it, and the avatar says it. Coming soon to EmoStream." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: TTS,
});

const MAX = 1000;
const FLOW = ["Text", "TTS", "Audio", "EmoStream engine"];

function TTS() {
  const soon = useComingSoon();
  const [text, setText] = useState("Hello — I'm a demonstration avatar. Everything I say is generated from a single portrait.");
  const [voice, setVoice] = useState("warm");
  const [lang, setLang] = useState("en");
  const [speed, setSpeed] = useState(1);
  const [pitch, setPitch] = useState(0);
  const explain = () =>
    soon({
      title: "Text to speech",
      body: "Speech generation isn't connected to a provider yet, so nothing is generated. When it is, the audio will drive the avatar exactly like your microphone does.",
      flow: FLOW,
    });

  return (
    <Page wide>
      <PageHeader
        label="Voice sources · Text to speech"
        title={<>Type it. Your avatar says it.</>}
        description="Write a script, choose a voice, and the generated speech animates your portrait. The layout is ready; the speech provider isn't connected yet."
        actions={<SoonBadge />}
      />
      <ol className="mt-6 flex flex-wrap items-center gap-2">
        {FLOW.map((f, i) => (
          <li key={f} className="flex items-center gap-2">
            <span className="timecode rounded border border-border bg-surface px-2.5 py-1 text-[11px] uppercase">{f}</span>
            {i < FLOW.length - 1 && <span className="h-px w-5 bg-border" />}
          </li>
        ))}
      </ol>

      <div className="mt-6 grid gap-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <section className="panel flex flex-col p-5">
          <label htmlFor="script" className="eyebrow text-muted-foreground">Script</label>
          <Textarea id="script" value={text} onChange={(e) => setText(e.target.value.slice(0, MAX))} className="font-display mt-3 min-h-[260px] flex-1 resize-none border-0 bg-transparent p-0 text-[1.6rem] leading-snug shadow-none focus-visible:ring-0" />
          <div className="mt-4 flex items-center justify-between border-t border-border pt-3">
            <span className={cn("timecode text-xs", text.length > MAX * 0.9 ? "text-ember" : "text-muted-foreground")}>{text.length} / {MAX}</span>
            <span className="text-xs text-muted-foreground">≈ {Math.max(1, Math.round(text.split(/\s+/).filter(Boolean).length / (2.5 * speed)))} s of speech</span>
          </div>
        </section>

        <section className="panel soon-surface space-y-5 p-5">
          <div>
            <p className="eyebrow mb-2 text-muted-foreground">Voice</p>
            <div className="flex gap-2">
              <Select value={voice} onValueChange={setVoice}>
                <SelectTrigger className="flex-1"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="warm">Warm · mid</SelectItem>
                  <SelectItem value="clear">Clear · bright</SelectItem>
                  <SelectItem value="low">Low · calm</SelectItem>
                </SelectContent>
              </Select>
              <Button variant="hairline" onClick={explain} aria-label="Preview voice"><Play /> Preview</Button>
            </div>
            <p className="mt-1.5 text-[11px] text-muted-foreground">Placeholder voice names until a provider is chosen.</p>
          </div>
          <div>
            <p className="eyebrow mb-2 text-muted-foreground">Language</p>
            <Select value={lang} onValueChange={setLang}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="en">English</SelectItem>
                <SelectItem value="ur">Urdu</SelectItem>
                <SelectItem value="es">Spanish</SelectItem>
                <SelectItem value="fr">French</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <SliderRow label="Speed" value={speed} display={`${speed.toFixed(2)}×`} min={0.5} max={2} step={0.05} onChange={setSpeed} />
          <SliderRow label="Pitch" value={pitch} display={`${pitch > 0 ? "+" : ""}${pitch} st`} min={-6} max={6} step={1} onChange={setPitch} />
          <div className="rounded-md border border-border bg-sunk p-3">
            <p className="eyebrow text-[10px] text-muted-foreground">Generated audio</p>
            <WaveformMotif bars={64} seed={9} className="mt-2 h-8 w-full text-foreground/15" />
            <p className="mt-1 text-[11px] text-muted-foreground">Nothing generated yet.</p>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Button variant="hairline" onClick={explain}><Wand2 /> Generate speech</Button>
            <Button variant="ink" onClick={explain}><Sparkles /> Animate avatar</Button>
          </div>
        </section>
      </div>
    </Page>
  );
}

function SliderRow({ label, value, display, min, max, step, onChange }: { label: string; value: number; display: string; min: number; max: number; step: number; onChange: (v: number) => void }) {
  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between">
        <p className="eyebrow text-muted-foreground">{label}</p>
        <span className="timecode text-sm">{display}</span>
      </div>
      <Slider value={[value]} min={min} max={max} step={step} onValueChange={([v]) => onChange(v ?? min)} aria-label={label} />
    </div>
  );
}
