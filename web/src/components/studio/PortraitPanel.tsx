import { AlertTriangle, Check, Crop, ImageUp, Loader2, RefreshCw, ScanFace } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { CropGuides } from "@/components/brand/HeroStage";
import {
  cropStyle,
  detectFace,
  loadImage,
  studioStore,
  useStudio,
  validatePortraitFile,
  validatePortraitSize,
  type FaceCheck,
} from "@/lib/studio-store";
import { useSettings } from "@/lib/settings";
import { cn } from "@/lib/utils";
import { CropDialog } from "./CropDialog";
import { PanelBlock } from "./PanelBlock";

export function PortraitPanel({
  preparing,
  setPreparing,
  locked,
}: {
  preparing: boolean;
  setPreparing: (b: boolean) => void;
  locked: boolean;
}) {
  const portrait = useStudio((s) => s.portrait);
  const consent = useStudio((s) => s.consent);
  const name = useStudio((s) => s.avatarName);
  const guides = useSettings((s) => s.showCropGuides);
  const [error, setError] = useState<string>();
  const [dragging, setDragging] = useState(false);
  const [cropOpen, setCropOpen] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  async function accept(file: File) {
    setError(undefined);
    const bad = validatePortraitFile(file);
    if (bad) return setError(bad);
    setPreparing(true);
    const url = URL.createObjectURL(file);
    try {
      const img = await loadImage(url);
      const tooSmall = validatePortraitSize(img.naturalWidth, img.naturalHeight);
      if (tooSmall) {
        URL.revokeObjectURL(url);
        setPreparing(false);
        return setError(tooSmall);
      }
      const faceCheck = await detectFace(url);
      const old = studioStore.get().portrait;
      if (old) URL.revokeObjectURL(old.url);
      studioStore.set({
        portrait: {
          url,
          name: file.name,
          type: file.type,
          sizeBytes: file.size,
          width: img.naturalWidth,
          height: img.naturalHeight,
          crop: { x: 0, y: -0.15, zoom: 1 },
          faceCheck,
          addedAt: Date.now(),
        },
        consent: false,
        avatarName:
          studioStore.get().avatarName === "Untitled avatar"
            ? file.name.replace(/\.[^.]+$/, "").slice(0, 40)
            : studioStore.get().avatarName,
      });
      // Done: the portrait is read and checked locally. It is uploaded to the engine only when
      // a session starts, and the engine's own face check is reported then.
      setPreparing(false);
    } catch {
      URL.revokeObjectURL(url);
      setPreparing(false);
      setError("This file couldn't be read as an image.");
    }
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    if (locked) return;
    const f = e.dataTransfer.files?.[0];
    if (f) accept(f);
  };

  return (
    <PanelBlock
      index="01"
      title="Portrait"
      hint={portrait ? `${portrait.width}×${portrait.height}` : "Required"}
    >
      <input
        ref={fileRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className="sr-only"
        aria-label="Upload portrait"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) accept(f);
          e.target.value = "";
        }}
      />

      <div
        onDragOver={(e) => {
          e.preventDefault();
          if (!locked) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          "relative aspect-square overflow-hidden rounded-lg border transition-colors duration-200",
          dragging
            ? "border-ember bg-ember/5"
            : portrait
              ? "border-border bg-stage"
              : "border-dashed border-input bg-sunk",
        )}
      >
        {portrait ? (
          <>
            <img
              src={portrait.url}
              alt="Your portrait"
              style={cropStyle(portrait)}
              className="select-none"
              draggable={false}
            />
            {guides && <CropGuides className="inset-3" />}
            {preparing && <PreparingOverlay />}
          </>
        ) : preparing ? (
          <PreparingOverlay />
        ) : (
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            className="flex h-full w-full flex-col items-center justify-center gap-3 p-6 text-center"
          >
            <PortraitGuideIllustration />
            <span className="text-sm font-medium">Upload a portrait to create your avatar</span>
            <span className="text-xs text-muted-foreground">Drop an image here, or browse</span>
          </button>
        )}
      </div>

      {error && (
        <p
          role="alert"
          className="mt-3 flex gap-2 rounded-md border border-destructive/30 bg-destructive/8 p-2.5 text-xs text-destructive"
        >
          <AlertTriangle className="mt-px size-3.5 shrink-0" /> {error}
        </p>
      )}

      {portrait ? (
        <>
          <div className="mt-3 flex gap-2">
            <Button
              variant="hairline"
              size="sm"
              className="flex-1"
              onClick={() => fileRef.current?.click()}
              disabled={locked}
            >
              <RefreshCw /> Replace
            </Button>
            <Button
              variant="hairline"
              size="sm"
              className="flex-1"
              onClick={() => setCropOpen(true)}
              disabled={locked}
            >
              <Crop /> Crop & position
            </Button>
          </div>
          <FaceStatus check={portrait.faceCheck} />
          <label className="mt-4 block">
            <span className="eyebrow text-[10px] text-muted-foreground">Avatar name</span>
            <Input
              value={name}
              maxLength={40}
              onChange={(e) => studioStore.set({ avatarName: e.target.value })}
              className="mt-1.5 h-9 bg-surface"
            />
          </label>
          <label
            className={cn(
              "mt-4 flex cursor-pointer gap-3 rounded-md border p-3 transition-colors",
              consent ? "border-success/40 bg-success/6" : "border-warning/50 bg-warning/8",
            )}
          >
            <Checkbox
              checked={consent}
              disabled={locked}
              onCheckedChange={(v) => studioStore.set({ consent: v === true })}
              className="mt-0.5"
              aria-label="Confirm portrait consent"
            />
            <span className="text-xs leading-relaxed">
              I have the right to use this portrait, and the person shown has agreed to it being
              animated.
            </span>
          </label>
          <CropDialog open={cropOpen} onOpenChange={setCropOpen} />
        </>
      ) : (
        <ul className="mt-4 space-y-1.5 text-xs text-muted-foreground">
          {[
            "One person, facing the camera",
            "Even light, eyes and mouth visible",
            "At least 512×512 px · JPG, PNG or WebP",
            "Up to 10 MB",
          ].map((r) => (
            <li key={r} className="flex items-center gap-2">
              <span className="h-px w-3 bg-ember" /> {r}
            </li>
          ))}
        </ul>
      )}
    </PanelBlock>
  );
}

function FaceStatus({ check }: { check: FaceCheck }) {
  const map: Record<FaceCheck, { icon: typeof Check; text: string; cls: string }> = {
    found: { icon: Check, text: "One face detected in your browser", cls: "text-success" },
    "not-found": {
      icon: AlertTriangle,
      text: "No face detected — try a clearer, front-facing photo",
      cls: "text-destructive",
    },
    multiple: {
      icon: AlertTriangle,
      text: "More than one face — use a portrait of one person",
      cls: "text-destructive",
    },
    unsupported: {
      icon: ScanFace,
      text: "Face check runs on the engine when the session starts",
      cls: "text-muted-foreground",
    },
    pending: { icon: Loader2, text: "Checking for a face…", cls: "text-muted-foreground" },
  };
  const m = map[check];
  return (
    <p className={cn("mt-3 flex items-center gap-2 text-xs", m.cls)}>
      <m.icon className={cn("size-3.5", check === "pending" && "animate-spin")} /> {m.text}
    </p>
  );
}

function PreparingOverlay() {
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-stage/70 text-stage-foreground">
      <div className="relative h-px w-2/3 overflow-hidden bg-stage-line">
        <div className="animate-scan absolute inset-y-0 w-1/3 bg-ember" />
      </div>
      <span className="eyebrow text-[10px] text-stage-muted">Preparing portrait</span>
    </div>
  );
}

function PortraitGuideIllustration() {
  return (
    <svg viewBox="0 0 120 120" className="h-24 w-24 text-muted-foreground" fill="none" aria-hidden>
      <rect
        x="10"
        y="10"
        width="100"
        height="100"
        rx="4"
        className="stroke-current"
        strokeDasharray="3 4"
      />
      <ellipse cx="60" cy="54" rx="20" ry="25" className="stroke-current" />
      <path d="M28 110c4-18 16-26 32-26s28 8 32 26" className="stroke-current" />
      <path d="M52 50h0M68 50h0" className="stroke-current" strokeWidth="3" strokeLinecap="round" />
      <path d="M54 64c4 2 8 2 12 0" className="stroke-ember" strokeLinecap="round" />
      <ImageUp x="88" y="14" width="18" height="18" className="text-ember" />
    </svg>
  );
}
