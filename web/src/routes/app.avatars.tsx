import { createFileRoute, Link } from "@tanstack/react-router";
import { Eye, Pencil, Play, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Page, PageHeader } from "@/components/app/PageHeader";
import { StatusPill } from "@/components/app/Status";
import { CropGuides } from "@/components/brand/HeroStage";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Input } from "@/components/ui/input";
import { cropStyle, studioStore, useStudio } from "@/lib/studio-store";

export const Route = createFileRoute("/app/avatars")({
  head: () => ({
    meta: [
      { title: "My Avatars — EmoStream" },
      { name: "description", content: "The portraits you've prepared for animation in EmoStream." },
      { property: "og:title", content: "My Avatars — EmoStream" },
      { property: "og:description", content: "Portraits prepared for animation in EmoStream." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: Avatars,
});

function Avatars() {
  const portrait = useStudio((s) => s.portrait);
  const name = useStudio((s) => s.avatarName);
  const consent = useStudio((s) => s.consent);
  const [preview, setPreview] = useState(false);
  const [edit, setEdit] = useState(false);
  const [del, setDel] = useState(false);
  const [draft, setDraft] = useState(name);

  return (
    <Page>
      <PageHeader
        label="Workspace · My Avatars"
        title="Your avatars"
        description="An avatar is one portrait, cropped and consented, ready to be animated. Saving a library across visits is planned; today an avatar lasts for this browser tab."
        actions={
          <Button asChild variant="ink">
            <Link to="/app/studio">
              <Plus /> New avatar
            </Link>
          </Button>
        }
      />

      {!portrait ? (
        <div className="mt-10 grid items-center gap-10 rounded-xl border border-dashed border-input p-8 md:grid-cols-[220px_1fr] md:p-12">
          <div className="stage relative mx-auto aspect-[4/5] w-48 overflow-hidden rounded-lg">
            <CropGuides />
            <svg viewBox="0 0 100 125" className="absolute inset-0 h-full w-full" aria-hidden>
              <ellipse
                cx="50"
                cy="52"
                rx="19"
                ry="24"
                fill="none"
                className="stroke-stage-foreground/40"
                strokeDasharray="2 3"
              />
              <path
                d="M18 125c4-22 16-32 32-32s28 10 32 32"
                fill="none"
                className="stroke-stage-foreground/30"
                strokeDasharray="2 3"
              />
            </svg>
          </div>
          <div>
            <h2 className="display-md">No avatars yet.</h2>
            <p className="mt-3 max-w-md text-muted-foreground">
              Create your first one in Studio: upload a front-facing portrait, check the crop, and
              confirm you have consent to animate it.
            </p>
            <ol className="mt-5 space-y-1.5 text-sm text-muted-foreground">
              <li>
                <span className="timecode mr-2 text-ember">01</span>Upload a portrait
              </li>
              <li>
                <span className="timecode mr-2 text-ember">02</span>Crop and position the face
              </li>
              <li>
                <span className="timecode mr-2 text-ember">03</span>Confirm consent
              </li>
            </ol>
            <Button asChild variant="ink" className="mt-6">
              <Link to="/app/studio">Create your first avatar</Link>
            </Button>
          </div>
        </div>
      ) : (
        <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1.1fr)_1fr]">
          <article className="group panel overflow-hidden">
            <div className="stage relative aspect-square overflow-hidden rounded-none">
              <img
                src={portrait.url}
                alt={name}
                style={cropStyle(portrait)}
                className="transition-transform duration-500 ease-soft"
              />
              <CropGuides />
              <span className="eyebrow absolute bottom-3 right-3 rounded-[3px] bg-stage/70 px-2 py-1 text-[9px] text-stage-foreground">
                Source portrait
              </span>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 p-5">
              <div className="min-w-0">
                <h2 className="font-display truncate text-3xl">{name}</h2>
                <p className="timecode mt-1 text-xs text-muted-foreground">
                  Created{" "}
                  {new Date(portrait.addedAt).toLocaleString(undefined, {
                    dateStyle: "medium",
                    timeStyle: "short",
                  })}{" "}
                  · {portrait.width}×{portrait.height}
                </p>
              </div>
              <StatusPill tone={consent ? "success" : "warning"} dot>
                {consent ? "Ready" : "Needs consent"}
              </StatusPill>
            </div>
            <div className="flex flex-wrap gap-2 border-t border-border p-4">
              <Button asChild variant="ink" size="sm">
                <Link to="/app/studio">
                  <Play /> Open in Studio
                </Link>
              </Button>
              <Button variant="hairline" size="sm" onClick={() => setPreview(true)}>
                <Eye /> Preview
              </Button>
              <Button
                variant="hairline"
                size="sm"
                onClick={() => {
                  setDraft(name);
                  setEdit(true);
                }}
              >
                <Pencil /> Rename
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="ml-auto text-destructive hover:text-destructive"
                onClick={() => setDel(true)}
              >
                <Trash2 /> Delete
              </Button>
            </div>
          </article>

          <aside className="space-y-4">
            <div className="panel p-5">
              <p className="eyebrow text-muted-foreground">Library</p>
              <p className="mt-2 text-sm text-muted-foreground">
                Keeping several avatars between visits needs storage the current engine doesn't
                provide. These slots show where they will live.
              </p>
              <div className="mt-4 grid grid-cols-3 gap-2">
                {[0, 1, 2, 3, 4, 5].map((i) => (
                  <div
                    key={i}
                    className="soon-surface flex aspect-square items-end rounded-md border border-dashed border-soon/50 p-2"
                  >
                    <span className="timecode text-[9px] text-soon">
                      SLOT {String(i + 2).padStart(2, "0")}
                    </span>
                  </div>
                ))}
              </div>
              <div className="mt-3">
                <StatusPill tone="soon">Persistent storage · planned</StatusPill>
              </div>
            </div>
          </aside>
        </div>
      )}

      <Dialog open={preview} onOpenChange={setPreview}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle className="font-display text-3xl font-normal">{name}</DialogTitle>
            <DialogDescription>
              The square EmoStream will animate. Change it with Crop & position in Studio.
            </DialogDescription>
          </DialogHeader>
          {portrait && (
            <div className="stage relative aspect-square overflow-hidden rounded-lg">
              <img src={portrait.url} alt="" style={cropStyle(portrait)} />
              <CropGuides />
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={edit} onOpenChange={setEdit}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Rename avatar</DialogTitle>
          </DialogHeader>
          <Input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            maxLength={40}
            aria-label="Avatar name"
            autoFocus
          />
          <DialogFooter>
            <Button variant="hairline" onClick={() => setEdit(false)}>
              Cancel
            </Button>
            <Button
              variant="ink"
              disabled={!draft.trim()}
              onClick={() => {
                studioStore.set({ avatarName: draft.trim() });
                setEdit(false);
              }}
            >
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={del} onOpenChange={setDel}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete “{name}”?</AlertDialogTitle>
            <AlertDialogDescription>
              The portrait is removed from this tab. It is only sent to the engine while a session
              runs and is not stored there, so there's nothing else to delete.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep it</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => {
                const p = studioStore.get().portrait;
                if (p) URL.revokeObjectURL(p.url);
                studioStore.set({ portrait: null, consent: false, avatarName: "Untitled avatar" });
              }}
            >
              Delete avatar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Page>
  );
}
