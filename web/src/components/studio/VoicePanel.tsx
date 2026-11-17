import { Link } from "@tanstack/react-router";
import {
  FileAudio,
  Headphones,
  RefreshCw,
  Upload,
  Loader2,
  Mic,
  MicOff,
  Pause,
  Play,
  Square,
  Type,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { LiveBars } from "@/components/brand/Waveform";
import { StatusPill } from "@/components/app/Status";
import { useRef, useState } from "react";
import { decodeAudioFile } from "@engine/audio";
import { duration } from "@/lib/format";
import { updateSettings, useSettings } from "@/lib/settings";
import { AUDIO_RULES, studioStore, useStudio, validateAudioFile } from "@/lib/studio-store";
import { cn } from "@/lib/utils";
import type { StudioSession } from "./useStudioSession";
import { PanelBlock } from "./PanelBlock";

export function VoicePanel({ s }: { s: StudioSession }) {
  const { mic, phase } = s;
  const deviceId = useSettings((x) => x.micDeviceId);
  const voiceConsent = useStudio((x) => x.voiceConsent);
  const source = useStudio((x) => x.voiceSource);
  const audioFile = useStudio((x) => x.audioFile);
  const fromFile = source === "file";
  const running = phase === "running";
  const paused = phase === "paused";
  const finishing = phase === "finishing";
  const live = running || paused;
  const bars =
    mic.history.length < 48
      ? [...Array(48 - mic.history.length).fill(0), ...mic.history]
      : mic.history.slice(-48);

  return (
    <PanelBlock index="02" title="Voice" hint={live ? duration(mic.elapsed) : undefined}>
      {/* source switch */}
      <div
        role="tablist"
        aria-label="Voice source"
        className="grid grid-cols-3 gap-1 rounded-md bg-sunk p-1"
      >
        <SourceTab
          active={!fromFile}
          icon={Mic}
          label="Microphone"
          disabled={live || finishing}
          onClick={() => studioStore.set({ voiceSource: "mic" })}
        />
        <SourceTab
          active={fromFile}
          icon={FileAudio}
          label="Audio file"
          disabled={live || finishing}
          onClick={() => studioStore.set({ voiceSource: "file" })}
        />
        <SourceTab icon={Type} label="Text" to />
      </div>

      <div className="mt-4 space-y-3">
        {fromFile ? (
          <AudioFilePicker locked={live || finishing} />
        ) : (
          <>
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
          </>
        )}

        {/* waveform + level */}
        <div className="rounded-md border border-border bg-sunk p-3">
          <div className="flex items-center justify-between">
            <span className="eyebrow flex items-center gap-1.5 text-[10px] text-muted-foreground">
              {running ? (
                <>
                  <span className="size-1.5 rounded-full bg-live animate-rec" />{" "}
                  {fromFile ? "Streaming" : "Listening"}
                </>
              ) : paused ? (
                "Paused"
              ) : (
                "Input level"
              )}
            </span>
            <span className="timecode text-[10.5px] text-muted-foreground">
              {live ? duration(mic.elapsed) : "0:00"}
            </span>
          </div>
          <LiveBars
            levels={bars}
            className={cn("mt-2 h-10 w-full", running ? "text-foreground" : "text-foreground/25")}
          />
          <LevelMeter level={mic.level} />
        </div>

        {mic.error && (
          <p role="alert" className="text-xs text-destructive">
            {mic.error}
          </p>
        )}
        {!fromFile && mic.state === "unsupported" && (
          <p className="text-xs text-destructive">This browser can't capture microphone audio.</p>
        )}

        <label
          className={cn(
            "flex cursor-pointer gap-3 rounded-md border p-3 transition-colors",
            voiceConsent ? "border-success/40 bg-success/6" : "border-warning/50 bg-warning/8",
          )}
        >
          <Checkbox
            checked={voiceConsent}
            disabled={live || finishing}
            onCheckedChange={(v) => studioStore.set({ voiceConsent: v === true })}
            className="mt-0.5"
            aria-label="Confirm voice consent"
          />
          <span className="text-xs leading-relaxed">
            {fromFile
              ? "The voice in this recording is mine, or the speaker agreed to it animating this avatar. It is sent to the EmoStream engine, isn't stored and isn't used to clone a voice."
              : "I agree to my microphone audio being sent to the EmoStream engine to animate this avatar. It isn't stored or used to clone a voice."}
          </span>
        </label>

        {fromFile ? (
          <div className="flex items-start gap-3 rounded-md border border-border bg-sunk p-3">
            <Headphones className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
            <p className="text-[11.5px] leading-snug text-muted-foreground">
              The recording plays here in step with the avatar, and is sent to the engine at
              speaking pace. When the take ends you can export it as an MP4 rendered by the engine.
            </p>
          </div>
        ) : (
          <div className="flex items-start gap-3 rounded-md border border-border bg-sunk p-3">
            <Headphones className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
            <label htmlFor="hear-avatar-voice" className="min-w-0 flex-1 cursor-pointer">
              <span className="block text-[12.5px] font-medium">Hear the avatar's voice</span>
              <span className="mt-0.5 block text-[11.5px] leading-snug text-muted-foreground">
                Plays your voice in step with the avatar's lips. Use headphones, or the microphone
                picks it up again.
              </span>
            </label>
            <Switch
              id="hear-avatar-voice"
              checked={s.hearVoice}
              onCheckedChange={s.setHearVoice}
              aria-label="Hear the avatar's voice"
            />
          </div>
        )}

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
              disabled={
                !s.canStart.ok ||
                (!fromFile && (mic.state === "requesting" || mic.state === "unsupported"))
              }
              title={s.canStart.ok ? undefined : s.canStart.reason}
            >
              <Mic />{" "}
              {mic.state === "requesting"
                ? "Waiting for permission…"
                : phase === "complete"
                  ? "Start new take"
                  : "Start session"}
            </Button>
          ) : (
            <>
              {running ? (
                <Button
                  variant="hairline"
                  className="flex-1"
                  onClick={s.pause}
                  disabled={s.conn !== "open"}
                >
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
        {!s.canStart.ok && !live && !finishing && (
          <p className="text-xs text-muted-foreground">{s.canStart.reason}</p>
        )}
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
  disabled,
}: {
  active?: boolean;
  icon: typeof Mic;
  label: string;
  onClick?: () => void;
  to?: boolean;
  disabled?: boolean;
}) {
  const cls = cn(
    "flex h-8 items-center justify-center gap-1.5 rounded-[5px] text-[12px] transition-colors disabled:cursor-not-allowed disabled:opacity-60",
    active
      ? "bg-surface font-medium text-foreground shadow-sm"
      : "text-muted-foreground hover:text-foreground",
  );
  if (to)
    return (
      <Link to="/app/text-to-speech" role="tab" aria-selected={false} className={cls}>
        <Icon className="size-3.5" /> {label}
      </Link>
    );
  return (
    <button
      type="button"
      role="tab"
      aria-selected={!!active}
      className={cls}
      onClick={onClick}
      disabled={!!disabled && !active}
    >
      <Icon className="size-3.5" /> {label}
    </button>
  );
}

/** Choose the recording that drives the avatar. Read in this tab only; never stored. */
function AudioFilePicker({ locked }: { locked: boolean }) {
  const clip = useStudio((x) => x.audioFile);
  const input = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string>();
  const [reading, setReading] = useState(false);

  async function accept(file: File) {
    setError(undefined);
    const bad = validateAudioFile(file);
    if (bad) return setError(bad);
    setReading(true);
    try {
      const { samples } = await decodeAudioFile(file);
      const durationS = samples.length / 16000;
      if (durationS < 0.5) throw new Error("short");
      studioStore.set({ audioFile: { file, name: file.name, sizeBytes: file.size, durationS } });
    } catch {
      setError("This file couldn't be read as audio. Try WAV or MP3.");
    } finally {
      setReading(false);
    }
  }

  return (
    <div className="space-y-2">
      <input
        ref={input}
        type="file"
        accept="audio/*,.wav,.mp3,.m4a,.ogg,.flac,.webm,.mpeg"
        className="sr-only"
        aria-label="Upload audio file"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) void accept(f);
          e.target.value = "";
        }}
      />
      <span className="eyebrow text-[10px] text-muted-foreground">Recording</span>
      {clip ? (
        <div className="flex items-center gap-3 rounded-md border border-border bg-surface p-3">
          <FileAudio className="size-4 shrink-0 text-ember" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-[12.5px] font-medium">{clip.name}</p>
            <p className="timecode text-[10.5px] text-muted-foreground">
              {duration(clip.durationS * 1000)} · {(clip.sizeBytes / 1024 / 1024).toFixed(1)} MB
            </p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => input.current?.click()}
            disabled={locked || reading}
          >
            <RefreshCw /> Replace
          </Button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => input.current?.click()}
          disabled={locked || reading}
          className="flex w-full items-center justify-center gap-2 rounded-md border border-dashed border-input bg-sunk px-3 py-4 text-[12.5px] text-muted-foreground transition-colors hover:text-foreground"
        >
          {reading ? <Loader2 className="size-4 animate-spin" /> : <Upload className="size-4" />}
          {reading ? "Reading audio…" : "Choose an audio file"}
        </button>
      )}
      {error && (
        <p role="alert" className="text-xs text-destructive">
          {error}
        </p>
      )}
      {clip && clip.durationS > AUDIO_RULES.exportSeconds && (
        <p className="text-[11.5px] text-muted-foreground">
          The MP4 export renders the first {AUDIO_RULES.exportSeconds / 60} minutes; the live take
          uses all of it.
        </p>
      )}
      <p className="text-[11.5px] text-muted-foreground">
        WAV, MP3, M4A, OGG or FLAC, up to 30 MB. Sent at speaking pace, so the avatar plays as it
        would live.
      </p>
    </div>
  );
}

function LevelMeter({ level }: { level: number }) {
  const segs = 24;
  const lit = Math.round(level * segs);
  return (
    <div
      className="mt-2 flex gap-[2px]"
      role="meter"
      aria-label="Input level"
      aria-valuenow={Math.round(level * 100)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      {Array.from({ length: segs }, (_, i) => (
        <span
          key={i}
          className={cn(
            "h-1.5 flex-1 rounded-[1px] transition-colors duration-75",
            i < lit
              ? i > segs * 0.85
                ? "bg-live"
                : i > segs * 0.65
                  ? "bg-warning"
                  : "bg-success"
              : "bg-border",
          )}
        />
      ))}
    </div>
  );
}

function PermissionPill({ p, state }: { p: string; state: string }) {
  if (state === "unsupported") return <StatusPill tone="muted">Unavailable</StatusPill>;
  if (p === "granted")
    return (
      <StatusPill tone="success" dot>
        Allowed
      </StatusPill>
    );
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
  const tone =
    s.conn === "open"
      ? "bg-success"
      : s.conn === "lost" || s.conn === "error"
        ? "bg-live"
        : s.conn === "connecting"
          ? "bg-warning"
          : "bg-muted-foreground/40";
  return (
    <p className="flex items-start gap-2 text-[11.5px] leading-snug text-muted-foreground">
      <span className={cn("mt-1 size-1.5 shrink-0 rounded-full", tone)} />
      <span className="min-w-0 break-words">
        {text}{" "}
        {!s.engineUrl && (
          <Link
            to="/app/settings"
            hash="performance"
            className="text-foreground underline underline-offset-2"
          >
            Connect
          </Link>
        )}
      </span>
    </p>
  );
}
