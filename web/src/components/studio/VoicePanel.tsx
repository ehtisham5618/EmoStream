import { Link } from "@tanstack/react-router";
import { FileAudio, Headphones, Loader2, Mic, MicOff, Pause, Play, Square, Type } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { LiveBars } from "@/components/brand/Waveform";
import { StatusPill } from "@/components/app/Status";
import { useComingSoon } from "@/components/app/ComingSoon";
import { duration } from "@/lib/format";
import { updateSettings, useSettings } from "@/lib/settings";
import { studioStore, useStudio } from "@/lib/studio-store";
import { cn } from "@/lib/utils";
import type { StudioSession } from "./useStudioSession";
import { PanelBlock } from "./PanelBlock";

export function VoicePanel({ s }: { s: StudioSession }) {
  const { mic, phase } = s;
  const deviceId = useSettings((x) => x.micDeviceId);
  const voiceConsent = useStudio((x) => x.voiceConsent);
  const soon = useComingSoon();
  const running = phase === "running";
  const paused = phase === "paused";
  const finishing = phase === "finishing";
  const live = running || paused;
  const bars = mic.history.length < 48 ? [...Array(48 - mic.history.length).fill(0), ...mic.history] : mic.history.slice(-48);

  return (
    <PanelBlock index="02" title="Voice" hint={live ? duration(mic.elapsed) : undefined}>
      {/* source switch */}
      <div role="tablist" aria-label="Voice source" className="grid grid-cols-3 gap-1 rounded-md bg-sunk p-1">
        <SourceTab active icon={Mic} label="Microphone" />
        <SourceTab
          icon={FileAudio}
          label="Audio file"
          onClick={() =>
            soon({
              title: "Audio file input",
              body: "The engine accepts recorded clips (the diagnostics client at /diagnostics/ streams them at speaking pace), but the Studio drives the avatar from the microphone in this build. File input here is planned.",
              flow: ["Audio file", "WavLM", "BehaviourNet", "Renderer"],
            })
          }
        />
        <SourceTab icon={Type} label="Text" to />
      </div>

      <div className="mt-4 space-y-3">
        <div className="flex items-center justify-between">
          <span className="eyebrow text-[10px] text-muted-foreground">Input device</span>
          <PermissionPill p={mic.permission} state={mic.state} />
        </div>
        <Select
          value={deviceId || "default"}
          onValueChange={(v) => updateSettings({ micDeviceId: v === "default" ? "" : v })}
          disabled={live || finishing}
        >
          <SelectTrigger className="h-9 bg-surface text-[13px]" aria-label="Microphone">
            <SelectValue placeholder="System default" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="default">System default</SelectItem>
            {mic.devices
              .filter((d) => d.deviceId && d.deviceId !== "default")
              .map((d, i) => (
                <SelectItem key={d.deviceId} value={d.deviceId}>
                  {d.label || `Microphone ${i + 1}`}
                </SelectItem>
              ))}
          </SelectContent>
        </Select>

        {/* waveform + level */}
        <div className="rounded-md border border-border bg-sunk p-3">
          <div className="flex items-center justify-between">
            <span className="eyebrow flex items-center gap-1.5 text-[10px] text-muted-foreground">
              {running ? (
                <>
                  <span className="size-1.5 rounded-full bg-live animate-rec" /> Listening
                </>
              ) : paused ? (
                "Paused"
              ) : (
                "Input level"
              )}
            </span>
            <span className="timecode text-[10.5px] text-muted-foreground">{live ? duration(mic.elapsed) : "0:00"}</span>
          </div>
          <LiveBars levels={bars} className={cn("mt-2 h-10 w-full", running ? "text-foreground" : "text-foreground/25")} />
          <LevelMeter level={mic.level} />
        </div>

        {mic.error && (
          <p role="alert" className="text-xs text-destructive">
            {mic.error}
          </p>
        )}
        {mic.state === "unsupported" && <p className="text-xs text-destructive">This browser can't capture microphone audio.</p>}

        <label className={cn("flex cursor-pointer gap-3 rounded-md border p-3 transition-colors", voiceConsent ? "border-success/40 bg-success/6" : "border-warning/50 bg-warning/8")}>
          <Checkbox
            checked={voiceConsent}
            disabled={live || finishing}
            onCheckedChange={(v) => studioStore.set({ voiceConsent: v === true })}
            className="mt-0.5"
            aria-label="Confirm voice consent"
          />
          <span className="text-xs leading-relaxed">
            I agree to my microphone audio being sent to the EmoStream engine to animate this avatar. It isn't stored or used to clone a voice.
          </span>
        </label>

        <div className="flex items-start gap-3 rounded-md border border-border bg-sunk p-3">
          <Headphones className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
          <label htmlFor="hear-avatar-voice" className="min-w-0 flex-1 cursor-pointer">
            <span className="block text-[12.5px] font-medium">Hear the avatar's voice</span>
            <span className="mt-0.5 block text-[11.5px] leading-snug text-muted-foreground">
              Plays your voice in step with the avatar's lips. Use headphones, or the microphone picks it up again.
            </span>
          </label>
          <Switch id="hear-avatar-voice" checked={s.hearVoice} onCheckedChange={s.setHearVoice} aria-label="Hear the avatar's voice" />
        </div>

        {/* transport */}
        <div className="flex gap-2">
          {finishing ? (
            <Button variant="live" className="flex-1" disabled>
              <Loader2 className="animate-spin" /> Finishing last frames…
            </Button>
          ) : !live ? (
            <Button
              variant="live"
              className="flex-1"
              onClick={s.start}
              disabled={!s.canStart.ok || mic.state === "requesting" || mic.state === "unsupported"}
              title={s.canStart.ok ? undefined : s.canStart.reason}
            >
              <Mic /> {mic.state === "requesting" ? "Waiting for permission…" : phase === "complete" ? "Start new take" : "Start session"}
            </Button>
          ) : (
            <>
              {running ? (
                <Button variant="hairline" className="flex-1" onClick={s.pause} disabled={s.conn !== "open"}>
                  <Pause /> Pause
                </Button>
              ) : (
                <Button variant="hairline" className="flex-1" onClick={s.resume}>
                  <Play /> Resume
                </Button>
              )}
              <Button variant="ink" className="flex-1" onClick={s.stop}>
                <Square className="fill-current" /> Stop
              </Button>
            </>
          )}
        </div>
        {!s.canStart.ok && !live && !finishing && <p className="text-xs text-muted-foreground">{s.canStart.reason}</p>}
        <ConnectionLine s={s} />
      </div>
    </PanelBlock>
  );
}

function SourceTab({
  active,
  icon: Icon,
  label,
  onClick,
  to,
}: {
  active?: boolean;
  icon: typeof Mic;
  label: string;
  onClick?: () => void;
  to?: boolean;
}) {
  const cls = cn(
    "flex h-8 items-center justify-center gap-1.5 rounded-[5px] text-[12px] transition-colors",
    active ? "bg-surface font-medium text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
  );
  if (to)
    return (
      <Link to="/app/text-to-speech" role="tab" aria-selected={false} className={cls}>
        <Icon className="size-3.5" /> {label}
      </Link>
    );
  return (
    <button type="button" role="tab" aria-selected={!!active} className={cls} onClick={onClick}>
      <Icon className="size-3.5" /> {label}
    </button>
  );
}

function LevelMeter({ level }: { level: number }) {
  const segs = 24;
  const lit = Math.round(level * segs);
  return (
    <div className="mt-2 flex gap-[2px]" role="meter" aria-label="Input level" aria-valuenow={Math.round(level * 100)} aria-valuemin={0} aria-valuemax={100}>
      {Array.from({ length: segs }, (_, i) => (
        <span
          key={i}
          className={cn(
            "h-1.5 flex-1 rounded-[1px] transition-colors duration-75",
            i < lit ? (i > segs * 0.85 ? "bg-live" : i > segs * 0.65 ? "bg-warning" : "bg-success") : "bg-border",
          )}
        />
      ))}
    </div>
  );
}

function PermissionPill({ p, state }: { p: string; state: string }) {
  if (state === "unsupported") return <StatusPill tone="muted">Unavailable</StatusPill>;
  if (p === "granted") return <StatusPill tone="success" dot>Allowed</StatusPill>;
  if (p === "denied")
    return (
      <StatusPill tone="live">
        <MicOff className="size-3" /> Blocked
      </StatusPill>
    );
  return <StatusPill tone="muted">Will ask</StatusPill>;
}

function ConnectionLine({ s }: { s: StudioSession }) {
  const text =
    s.conn === "connecting"
      ? "Connecting to engine…"
      : s.conn === "open"
        ? s.phase === "paused"
          ? "Connected · audio paused"
          : "Streaming to engine"
        : s.conn === "lost"
          ? "Connection lost"
          : s.conn === "error"
            ? "Engine error"
            : `Engine: ${s.engineUrl}`;
  const tone = s.conn === "open" ? "bg-success" : s.conn === "lost" || s.conn === "error" ? "bg-live" : s.conn === "connecting" ? "bg-warning" : "bg-muted-foreground/40";
  return (
    <p className="flex items-start gap-2 text-[11.5px] leading-snug text-muted-foreground">
      <span className={cn("mt-1 size-1.5 shrink-0 rounded-full", tone)} />
      <span className="min-w-0 break-words">
        {text}{" "}
        {!s.engineUrl && (
          <Link to="/app/settings" hash="performance" className="text-foreground underline underline-offset-2">
            Connect
          </Link>
        )}
      </span>
    </p>
  );
}
