import { Link } from "@tanstack/react-router";
import { Check, Download, Loader2, RotateCcw, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useEngineStatus } from "@/lib/engine/useEngineStatus";
import { useStudio } from "@/lib/studio-store";
import { cn } from "@/lib/utils";
import type { StudioSession } from "./useStudioSession";
import { PanelBlock } from "./PanelBlock";

export function SessionPanel({ s }: { s: StudioSession }) {
  const portrait = useStudio((x) => x.portrait);
  const consent = useStudio((x) => x.consent);
  const voiceConsent = useStudio((x) => x.voiceConsent);
  const engine = useEngineStatus();
  const count = useStudio((x) => x.sessions.length);
  const audioFile = useStudio((x) => x.audioFile);
  // Microphone takes: Export = this browser's recording (engine frames + the avatar's voice).
  // Audio-file takes: Export = an MP4 rendered by the engine from the portrait and the recording
  // (POST /api/export); the browser recording stays available as WebM.
  const done = s.phase === "complete" && s.stats.framesReceived > 0;
  const fileTake = s.takeSource === "file";
  const canExport = done && (fileTake ? !!audioFile : !!s.recordingUrl);
  const busy = s.exporting || s.exportingMp4;

  const checks = [
    { ok: !!portrait, label: "Portrait uploaded" },
    { ok: consent, label: "Portrait consent confirmed" },
    { ok: voiceConsent, label: "Voice consent confirmed" },
    s.voiceSource === "file"
      ? { ok: !!audioFile, label: audioFile ? "Audio file chosen" : "No audio file yet" }
      : { ok: s.mic.permission === "granted", label: "Microphone allowed", soft: true },
    {
      ok: engine.status === "online",
      label:
        engine.status === "online"
          ? "Engine online"
          : engine.status === "checking"
            ? "Checking engine…"
            : "Engine not reachable",
      soft: true,
    },
  ];

  return (
    <PanelBlock index="05" title="Session" hint={count ? `${count} this visit` : undefined}>
      <ul className="space-y-1.5">
        {checks.map((c) => (
          <li key={c.label} className="flex items-center gap-2 text-[12.5px]">
            <span
              className={cn(
                "inline-flex size-4 items-center justify-center rounded-full",
                c.ok
                  ? "bg-success/15 text-success"
                  : c.soft
                    ? "bg-muted text-muted-foreground"
                    : "bg-warning/20 text-foreground",
              )}
            >
              {c.ok ? (
                <Check className="size-2.5" strokeWidth={3} />
              ) : (
                <X className="size-2.5" strokeWidth={3} />
              )}
            </span>
            <span className={c.ok ? "" : "text-muted-foreground"}>{c.label}</span>
          </li>
        ))}
      </ul>

      <div className="mt-4 grid grid-cols-2 gap-2">
        <Tooltip>
          <TooltipTrigger asChild>
            <span tabIndex={canExport ? -1 : 0}>
              <Button
                variant="hairline"
                size="sm"
                className="w-full"
                disabled={!canExport || busy}
                onClick={fileTake ? s.doExportMp4 : s.doExport}
              >
                {busy ? <Loader2 className="animate-spin" /> : <Download />}{" "}
                {s.exportingMp4 ? "Rendering MP4…" : fileTake ? "Export MP4" : "Export"}
              </Button>
            </span>
          </TooltipTrigger>
          <TooltipContent>
            {fileTake
              ? "The engine renders the portrait and your recording to a watermarked MP4, with the emotion the take started with"
              : "Downloads this take as recorded in your browser, once a rendered session is complete"}
          </TooltipContent>
        </Tooltip>
        <Button variant="ghost" size="sm" onClick={s.reset} disabled={s.phase === "idle"}>
          <RotateCcw /> New take
        </Button>
      </div>
      {done && fileTake && s.recordingUrl && (
        <button
          type="button"
          onClick={s.doExport}
          disabled={busy}
          className="mt-2 text-[11.5px] text-muted-foreground underline underline-offset-2 hover:text-foreground"
        >
          Download the browser recording (WebM) instead
        </button>
      )}
      <p className="mt-3 text-[11.5px] leading-relaxed text-muted-foreground">
        The current engine doesn't keep session history. Takes from this visit are listed in{" "}
        <Link to="/app/sessions" className="text-foreground underline underline-offset-2">
          Sessions
        </Link>{" "}
        until you close the tab.
      </p>
    </PanelBlock>
  );
}
