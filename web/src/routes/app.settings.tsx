import { createFileRoute } from "@tanstack/react-router";
import { Loader2, Lock, Mic, Moon, Monitor, Sun } from "lucide-react";
import { useState, type ReactNode } from "react";
import { toast } from "sonner";
import { Page, PageHeader } from "@/components/app/PageHeader";
import { SoonBadge, StatusPill } from "@/components/app/Status";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { LiveBars } from "@/components/brand/Waveform";
import { useMicrophone } from "@/lib/audio/useMicrophone";
import { fetchEngineInfo } from "@/lib/engine/client";
import { EMOTIONS, type EmotionId } from "@/lib/emotions";
import { resetSettings, updateSettings, useSettings, type ThemePref } from "@/lib/settings";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/app/settings")({
  head: () => ({
    meta: [
      { title: "Settings — EmoStream" },
      { name: "description", content: "Theme, Studio defaults, microphone, privacy, engine connection and account settings for EmoStream." },
      { property: "og:title", content: "Settings — EmoStream" },
      { property: "og:description", content: "Configure EmoStream Studio and its engine connection." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: Settings,
});

const SECTIONS = [
  ["general", "General"],
  ["studio", "Studio"],
  ["audio", "Audio"],
  ["privacy", "Privacy"],
  ["performance", "Performance"],
  ["account", "Account & workspace"],
] as const;

function Settings() {
  const s = useSettings((x) => x);
  return (
    <Page wide>
      <PageHeader label="Preferences · Settings" title="Settings" description="Saved in this browser. Settings marked Coming soon need backend work that doesn't exist yet." actions={<Button variant="ghost" size="sm" onClick={() => { resetSettings(); toast.success("Settings reset to defaults"); }}>Reset to defaults</Button>} />
      <div className="mt-8 grid gap-10 lg:grid-cols-[200px_minmax(0,1fr)]">
        <nav className="hidden lg:block" aria-label="Settings sections">
          <ul className="sticky top-8 space-y-px border-l border-border">
            {SECTIONS.map(([id, label], i) => (
              <li key={id}>
                <a href={`#${id}`} className="-ml-px flex items-center gap-3 border-l border-transparent py-1.5 pl-4 text-sm text-muted-foreground hover:border-foreground hover:text-foreground">
                  <span className="timecode text-[10px] text-ember">0{i + 1}</span>{label}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div className="space-y-12">
          <Section id="general" n="01" title="General">
            <Field label="Theme" hint="Light is warm and editorial; dark is the cinematic studio.">
              <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label="Theme">
                {([["light", "Light", Sun], ["dark", "Dark", Moon], ["system", "System", Monitor]] as const).map(([v, l, Icon]) => (
                  <button key={v} role="radio" aria-checked={s.theme === v} onClick={() => updateSettings({ theme: v as ThemePref })} className={cn("flex items-center justify-center gap-2 rounded-md border py-2.5 text-sm transition-colors", s.theme === v ? "border-foreground bg-surface font-medium" : "border-border text-muted-foreground hover:border-foreground/40")}>
                    <Icon className="size-4" /> {l}
                  </button>
                ))}
              </div>
            </Field>
            <Field label="Language" hint="The interface is written in English. Other languages are planned." soon>
              <Select value="en" disabled><SelectTrigger className="w-56"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="en">English</SelectItem></SelectContent></Select>
            </Field>
            <Field label="Reduced motion" hint="EmoStream follows your operating system's reduce-motion setting automatically.">
              <StatusPill tone="muted">Follows system</StatusPill>
            </Field>
          </Section>

          <Section id="studio" n="02" title="Studio">
            <Field label="Default emotion" hint="Applied when Studio opens.">
              <Select value={s.defaultEmotion} onValueChange={(v) => updateSettings({ defaultEmotion: v as EmotionId })}>
                <SelectTrigger className="w-56"><SelectValue /></SelectTrigger>
                <SelectContent>{EMOTIONS.map((e) => <SelectItem key={e.id} value={e.id}>{e.label}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
            <Field label="Default intensity" hint={`${s.defaultIntensity}%`}>
              <Slider className="max-w-sm" value={[s.defaultIntensity]} min={0} max={100} step={1} onValueChange={([v]) => updateSettings({ defaultIntensity: v ?? 0 })} aria-label="Default intensity" />
            </Field>
            <Field label="Output resolution" hint="The current model renders 512×512 only.">
              <Select value="512" disabled><SelectTrigger className="w-56"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="512">512 × 512</SelectItem></SelectContent></Select>
            </Field>
            <Toggle label="Crop guides" hint="Corner marks and centre cross on portraits and the preview." checked={s.showCropGuides} onChange={(v) => updateSettings({ showCropGuides: v })} />
            <Toggle label="Frame information" hint="Frame number and FPS in the preview corner." checked={s.showFrameInfo} onChange={(v) => updateSettings({ showFrameInfo: v })} />
            <Toggle label="Open telemetry by default" hint="Expand the technical panel under the timeline." checked={s.showTelemetry} onChange={(v) => updateSettings({ showTelemetry: v })} />
          </Section>

          <Section id="audio" n="03" title="Audio">
            <MicTest />
          </Section>

          <Section id="privacy" n="04" title="Privacy">
            <Locked label="Portrait consent" hint="Every portrait needs a consent confirmation before a session can start." />
            <Locked label="AI disclosure" hint="An “AI-generated” watermark is drawn on every preview frame. It can't be removed." />
            <Field label="Audio consent" hint="Your browser asks before any microphone use. Audio is streamed only while a session runs and isn't recorded by this interface.">
              <StatusPill tone="success" dot>Browser-managed</StatusPill>
            </Field>
            <Field label="Retention" hint="Portraits stay in this tab's memory and are discarded when it closes. What a connected engine keeps depends on how it's deployed.">
              <StatusPill tone="muted">Tab only</StatusPill>
            </Field>
            <Field label="Data preferences" hint="Choosing what an engine may keep needs server-side support." soon>
              <Switch disabled aria-label="Allow engine retention" />
            </Field>
          </Section>

          <Section id="performance" n="05" title="Performance">
            <EngineField />
            <Field label="GPU configuration" hint="Reported by the engine through /api/info. Not adjustable from the browser." soon>
              <Select disabled><SelectTrigger className="w-56"><SelectValue placeholder="Engine default" /></SelectTrigger><SelectContent><SelectItem value="d">Engine default</SelectItem></SelectContent></Select>
            </Field>
            <Field label="Rendering preferences" hint="Quality / speed trade-offs need engine support." soon>
              <Select disabled><SelectTrigger className="w-56"><SelectValue placeholder="Balanced" /></SelectTrigger><SelectContent><SelectItem value="b">Balanced</SelectItem></SelectContent></Select>
            </Field>
            <Field label="Streaming transport" hint="WebSocket frames today. WebRTC is planned.">
              <StatusPill tone="muted">WebSocket</StatusPill>
            </Field>
          </Section>

          <Section id="account" n="06" title="Account & workspace">
            <p className="text-sm text-muted-foreground">EmoStream's research build has no accounts. Nothing here is tied to a person.</p>
            <Field label="Profile" soon hint="Name and avatar for your workspace."><Input disabled placeholder="—" className="w-64" /></Field>
            <Field label="Workspace" soon hint="Shared avatars and sessions for a team."><Input disabled placeholder="Personal (this browser)" className="w-64" /></Field>
            <Field label="Account preferences" soon hint="Email, sign-in method, deletion."><Button variant="hairline" size="sm" disabled>Manage account</Button></Field>
          </Section>
        </div>
      </div>
    </Page>
  );
}

function Section({ id, n, title, children }: { id: string; n: string; title: string; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-8">
      <h2 className="flex items-baseline gap-3 border-b border-border pb-3">
        <span className="timecode text-xs text-ember">{n}</span>
        <span className="font-display text-[2rem] leading-none">{title}</span>
      </h2>
      <div className="divide-y divide-border">{children}</div>
    </section>
  );
}

function Field({ label, hint, children, soon }: { label: string; hint?: ReactNode; children: ReactNode; soon?: boolean }) {
  return (
    <div className="grid gap-3 py-5 md:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] md:items-center">
      <div>
        <p className="flex items-center gap-2 text-sm font-medium">{label} {soon && <SoonBadge />}</p>
        {hint && <p className="mt-1 text-[13px] text-muted-foreground">{hint}</p>}
      </div>
      <div className={cn(soon && "opacity-70")}>{children}</div>
    </div>
  );
}

function Toggle({ label, hint, checked, onChange }: { label: string; hint: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <Field label={label} hint={hint}>
      <Switch checked={checked} onCheckedChange={onChange} aria-label={label} />
    </Field>
  );
}

function Locked({ label, hint }: { label: string; hint: string }) {
  return (
    <Field label={label} hint={hint}>
      <span className="inline-flex items-center gap-2 text-sm text-muted-foreground"><Lock className="size-3.5" /> Always on</span>
    </Field>
  );
}

function MicTest() {
  const deviceId = useSettings((s) => s.micDeviceId);
  const mic = useMicrophone({ deviceId: deviceId || undefined });
  const testing = mic.state === "recording";
  return (
    <>
      <Field label="Microphone" hint="Used by Studio. Labels appear after you allow access once.">
        <Select value={deviceId || "default"} onValueChange={(v) => updateSettings({ micDeviceId: v === "default" ? "" : v })}>
          <SelectTrigger className="w-full max-w-sm"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="default">System default</SelectItem>
            {mic.devices.filter((d) => d.deviceId && d.deviceId !== "default").map((d, i) => (
              <SelectItem key={d.deviceId} value={d.deviceId}>{d.label || `Microphone ${i + 1}`}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>
      <Field label="Input level" hint={mic.error ?? (testing ? "Speak normally — the bars should reach the middle." : "Run a short test. Nothing is sent anywhere.")}>
        <div className="flex max-w-sm items-center gap-3">
          <div className="h-10 flex-1 rounded-md border border-border bg-sunk px-2">
            <LiveBars levels={mic.history.slice(-60)} className={cn("h-full w-full", testing ? "text-foreground" : "text-foreground/25")} />
          </div>
          {testing ? (
            <Button variant="ink" size="sm" onClick={mic.stop}>Stop</Button>
          ) : (
            <Button variant="hairline" size="sm" onClick={mic.start} disabled={mic.state === "requesting" || mic.state === "unsupported"}>
              {mic.state === "requesting" ? <Loader2 className="animate-spin" /> : <Mic />} Test
            </Button>
          )}
        </div>
      </Field>
    </>
  );
}

function EngineField() {
  const engineUrl = useSettings((s) => s.engineUrl);
  const [draft, setDraft] = useState(engineUrl);
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<string>();

  const test = async (url: string) => {
    setTesting(true);
    setResult(undefined);
    const r = await fetchEngineInfo(url);
    setTesting(false);
    setResult(r.ok ? `Connected · /api/info answered in ${r.latencyMs} ms` : r.error);
    return r.ok;
  };

  return (
    <Field label="Engine address" hint="Base URL of a running EmoStream engine. Studio connects to /ws/session there; leave empty to use the interface without rendering.">
      <form
        className="max-w-md space-y-2"
        onSubmit={async (e) => {
          e.preventDefault();
          const v = draft.trim();
          if (v && !/^https?:\/\//i.test(v)) {
            setResult("Start the address with http:// or https://");
            return;
          }
          updateSettings({ engineUrl: v });
          if (!v) {
            toast("Engine disconnected");
            return;
          }
          const ok = await test(v);
          toast[ok ? "success" : "error"](ok ? "Engine connected" : "Saved, but the engine didn't answer");
        }}
      >
        <div className="flex gap-2">
          <Input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="http://localhost:8000" className="timecode text-[13px]" aria-label="Engine address" />
          <Button type="submit" variant="ink" disabled={testing}>{testing ? <Loader2 className="animate-spin" /> : null} Save & test</Button>
        </div>
        {result && <p className="text-xs text-muted-foreground" role="status">{result}</p>}
      </form>
    </Field>
  );
}
