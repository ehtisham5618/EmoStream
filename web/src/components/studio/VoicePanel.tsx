import { Link } from "@tanstack/react-router";
import { FileAudio, Mic, MicOff, Pause, Play, Square, Type } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { LiveBars } from "@/components/brand/Waveform";
import { StatusPill } from "@/components/app/Status";
import { useComingSoon } from "@/components/app/ComingSoon";
import { duration } from "@/lib/format";
import { updateSettings, useSettings } from "@/lib/settings";
import { cn } from "@/lib/utils";
import type { StudioSession } from "./useStudioSession";
import { PanelBlock } from "./PanelBlock";

export function VoicePanel({ s }: { s: StudioSession }) {
  const { mic, phase } = s;
  const deviceId = useSettings((x) => x.micDeviceId);
  const soon = useComingSoon();
  const running = phase === "running";
  const paused = phase === "paused";
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
              body: "Uploading a recorded clip isn't confirmed on the current engine, so it isn't offered as a working option. It will appear here once the engine accepts file input.",
              flow: ["Audio file", "HuBERT", "BehaviourNet", "Renderer"],
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
          disabled={live}
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

        {/* transport */}
        <div className="flex gap-2">
          {!live ? (
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
                <Button variant="hairline" className="flex-1" onClick={s.pause}>
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
        {!s.canStart.ok && !live && <p className="text-xs text-muted-foreground">{s.canStart.reason}</p>}
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
  const text = !s.engineUrl
    ? "No engine connected — voice is captured locally, no frames are rendered."
    : s.conn === "connecting"
      ? "Connecting to engine…"
      : s.conn === "open"
        ? "Streaming to engine"
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
