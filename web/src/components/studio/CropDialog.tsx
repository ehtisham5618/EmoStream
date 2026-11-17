import { useEffect, useRef, useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { CropGuides } from "@/components/brand/HeroStage";
import { cropStyle, studioStore, useStudio, type Crop } from "@/lib/studio-store";

const clamp = (n: number) => Math.max(-1, Math.min(1, n));

export function CropDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const portrait = useStudio((s) => s.portrait);
  const [crop, setCrop] = useState<Crop>({ x: 0, y: 0, zoom: 1 });
  const drag = useRef<{ x: number; y: number; c: Crop } | null>(null);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open && portrait) setCrop(portrait.crop);
  }, [open, portrait]);

  if (!portrait) return null;
  const preview = { ...portrait, crop };

  const onKey = (e: React.KeyboardEvent) => {
    const step = 0.05;
    const map: Record<string, Partial<Crop>> = {
      ArrowLeft: { x: clamp(crop.x - step) },
      ArrowRight: { x: clamp(crop.x + step) },
      ArrowUp: { y: clamp(crop.y - step) },
      ArrowDown: { y: clamp(crop.y + step) },
    };
    if (map[e.key]) {
      e.preventDefault();
      setCrop({ ...crop, ...map[e.key] });
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="font-display text-3xl font-normal">Crop & position</DialogTitle>
          <DialogDescription>
            Drag to centre the face. Keep the chin and the top of the head inside the guides — EmoStream animates a 512×512 square.
          </DialogDescription>
        </DialogHeader>
        <div
          ref={box}
          tabIndex={0}
          onKeyDown={onKey}
          aria-label="Portrait crop area. Use arrow keys to move."
          className="stage relative aspect-square cursor-grab touch-none overflow-hidden rounded-lg active:cursor-grabbing"
          onPointerDown={(e) => {
            (e.target as HTMLElement).setPointerCapture(e.pointerId);
            drag.current = { x: e.clientX, y: e.clientY, c: crop };
          }}
          onPointerMove={(e) => {
            if (!drag.current || !box.current) return;
            const size = box.current.clientWidth;
            const dx = (e.clientX - drag.current.x) / size;
            const dy = (e.clientY - drag.current.y) / size;
            const k = 2.2 / Math.max(1, crop.zoom * 0.9);
            setCrop({ ...crop, x: clamp(drag.current.c.x - dx * k), y: clamp(drag.current.c.y - dy * k) });
          }}
          onPointerUp={() => (drag.current = null)}
        >
          <img src={portrait.url} alt="" style={cropStyle(preview)} draggable={false} className="pointer-events-none select-none" />
          <CropGuides className="inset-3" />
          <svg viewBox="0 0 100 100" className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden>
            <ellipse cx="50" cy="46" rx="21" ry="28" fill="none" className="stroke-stage-foreground/50" strokeDasharray="1.5 2" strokeWidth="0.4" />
          </svg>
          <span className="eyebrow absolute bottom-3 left-1/2 -translate-x-1/2 text-[9px] text-stage-muted">Face area</span>
        </div>
        <div className="flex items-center gap-4">
          <span className="eyebrow w-12 text-muted-foreground">Zoom</span>
          <Slider value={[crop.zoom]} min={1} max={3} step={0.01} onValueChange={([z]) => setCrop({ ...crop, zoom: z ?? 1 })} aria-label="Zoom" />
          <span className="timecode w-12 text-right text-xs">{crop.zoom.toFixed(2)}×</span>
        </div>
        <DialogFooter className="gap-2 sm:justify-between">
          <Button variant="ghost" onClick={() => setCrop({ x: 0, y: 0, zoom: 1 })}>
            Reset
          </Button>
          <div className="flex gap-2">
            <Button variant="hairline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button
              variant="ink"
              onClick={() => {
                studioStore.set((s) => ({ portrait: s.portrait ? { ...s.portrait, crop } : null }));
                onOpenChange(false);
              }}
            >
              Apply crop
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
