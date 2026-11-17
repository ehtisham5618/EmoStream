import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowDownUp, Download, Search, Trash2, X } from "lucide-react";
import { useMemo, useState } from "react";
import { Page, PageHeader, SectionTitle } from "@/components/app/PageHeader";
import { DemoNote, StatusPill } from "@/components/app/Status";
import { useComingSoon } from "@/components/app/ComingSoon";
import { FrameStrip } from "@/components/brand/FrameStrip";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
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
import { DEMO_SESSIONS, type DemoSession } from "@/lib/demo-data";
import { EMOTIONS, emotionById, type EmotionId } from "@/lib/emotions";
import { duration } from "@/lib/format";
import { useStudio } from "@/lib/studio-store";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/app/sessions")({
  head: () => ({
    meta: [
      { title: "Sessions — EmoStream" },
      { name: "description", content: "Takes recorded in EmoStream Studio, with search, filters and export." },
      { property: "og:title", content: "Sessions — EmoStream" },
      { property: "og:description", content: "Takes recorded in EmoStream Studio." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: Sessions,
});

type Sort = "newest" | "oldest" | "longest" | "name";

function Sessions() {
  const visit = useStudio((s) => s.sessions);
  const soon = useComingSoon();
  const [rows, setRows] = useState<DemoSession[]>(DEMO_SESSIONS);
  const [q, setQ] = useState("");
  const [emotion, setEmotion] = useState<EmotionId | "all">("all");
  const [status, setStatus] = useState<string>("all");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [sort, setSort] = useState<Sort>("newest");
  const [detail, setDetail] = useState<DemoSession | null>(null);
  const [confirm, setConfirm] = useState<DemoSession | null>(null);

  const filtered = useMemo(() => {
    let r = rows.filter((s) => {
      if (q && !`${s.name} ${s.avatar}`.toLowerCase().includes(q.toLowerCase())) return false;
      if (emotion !== "all" && s.emotion !== emotion) return false;
      if (status !== "all" && s.status !== status) return false;
      if (from && s.createdAt < from) return false;
      if (to && s.createdAt > to) return false;
      return true;
    });
    r = [...r].sort((a, b) =>
      sort === "newest" ? b.createdAt.localeCompare(a.createdAt) : sort === "oldest" ? a.createdAt.localeCompare(b.createdAt) : sort === "longest" ? b.durationS - a.durationS : a.name.localeCompare(b.name),
    );
    return r;
  }, [rows, q, emotion, status, from, to, sort]);

  const anyFilter = q || emotion !== "all" || status !== "all" || from || to;
  const exportSoon = () =>
    soon({
      title: "Export from history",
      body: "Exporting an old take needs the engine to keep finished sessions. It doesn't yet, so export is only available in Studio right after a rendered take.",
    });

  return (
    <Page wide>
      <PageHeader
        label="Workspace · Sessions"
        title="Sessions"
        description="A library of takes. The current engine doesn't store history, so the records below the line are demonstration data that show how the library will work."
      />

      {/* Real takes from this visit */}
      <section className="mt-8">
        <SectionTitle label="This visit" title="Takes from this tab" aside={<StatusPill tone="success" dot>Real records</StatusPill>} />
        {visit.length === 0 ? (
          <p className="rounded-lg border border-border bg-sunk px-4 py-5 text-sm text-muted-foreground">
            No takes yet. Run a session in{" "}
            <Link to="/app/studio" className="text-foreground underline underline-offset-2">
              Studio
            </Link>{" "}
            and it will appear here until you close the tab.
          </p>
        ) : (
          <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {visit.map((s) => {
              const e = emotionById(s.finalEmotion);
              return (
                <li key={s.id} className="panel p-4">
                  <div className="flex items-center justify-between">
                    <p className="font-medium">{s.avatarName}</p>
                    <span className="timecode text-xs text-muted-foreground">{duration(s.durationMs)}</span>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {new Date(s.startedAt).toLocaleTimeString()} · Microphone · {e.label} {s.finalIntensity}% · {s.emotionChanges} change(s)
                  </p>
                  <p className="mt-2 text-xs">{s.engine ? `${s.framesReceived} frames rendered` : "Not rendered — no engine connected"}</p>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {/* Demo library */}
      <section className="mt-12">
        <SectionTitle label="Library preview" title="How saved sessions will look" aside={<DemoNote>Demonstration data · not real sessions</DemoNote>} />

        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-surface p-2">
          <div className="relative min-w-[200px] flex-1">
            <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search sessions or avatars" className="h-9 border-0 bg-transparent pl-8 shadow-none focus-visible:ring-0" aria-label="Search sessions" />
          </div>
          <Select value={emotion} onValueChange={(v) => setEmotion(v as EmotionId | "all")}>
            <SelectTrigger className="h-9 w-[140px]" aria-label="Filter by emotion"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All emotions</SelectItem>
              {EMOTIONS.map((e) => <SelectItem key={e.id} value={e.id}>{e.label}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger className="h-9 w-[140px]" aria-label="Filter by status"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              <SelectItem value="Complete">Complete</SelectItem>
              <SelectItem value="Exported">Exported</SelectItem>
              <SelectItem value="Interrupted">Interrupted</SelectItem>
            </SelectContent>
          </Select>
          <div className="flex items-center gap-1">
            <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="h-9 w-[140px]" aria-label="From date" />
            <span className="text-muted-foreground">–</span>
            <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="h-9 w-[140px]" aria-label="To date" />
          </div>
          <Select value={sort} onValueChange={(v) => setSort(v as Sort)}>
            <SelectTrigger className="h-9 w-[150px]" aria-label="Sort"><ArrowDownUp className="size-3.5" /><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="newest">Newest first</SelectItem>
              <SelectItem value="oldest">Oldest first</SelectItem>
              <SelectItem value="longest">Longest first</SelectItem>
              <SelectItem value="name">Name A–Z</SelectItem>
            </SelectContent>
          </Select>
          {anyFilter && (
            <Button variant="ghost" size="sm" onClick={() => { setQ(""); setEmotion("all"); setStatus("all"); setFrom(""); setTo(""); }}>
              <X /> Clear
            </Button>
          )}
        </div>

        <div className="mt-3 overflow-x-auto rounded-lg border border-border">
          <table className="w-full min-w-[860px] text-sm">
            <thead className="bg-sunk text-left">
              <tr className="eyebrow text-[10px] text-muted-foreground">
                <th className="px-4 py-3 font-medium">Session</th>
                <th className="px-3 py-3 font-medium">Input</th>
                <th className="px-3 py-3 font-medium">Emotion</th>
                <th className="px-3 py-3 font-medium">Duration</th>
                <th className="px-3 py-3 font-medium">Created</th>
                <th className="px-3 py-3 font-medium">Status</th>
                <th className="px-3 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border bg-surface">
              {filtered.map((s) => {
                const e = emotionById(s.emotion);
                return (
                  <tr key={s.id} className="cursor-pointer transition-colors hover:bg-accent/40" onClick={() => setDetail(s)}>
                    <td className="px-4 py-3">
                      <p className="font-medium">{s.name}</p>
                      <p className="text-xs text-muted-foreground">{s.avatar}</p>
                    </td>
                    <td className="px-3 py-3 text-muted-foreground">{s.input}</td>
                    <td className="px-3 py-3">
                      <span className="flex items-center gap-2">
                        <span className={cn("size-2 rounded-full", e.bgClass)} /> {e.label}
                        <span className="timecode text-xs text-muted-foreground">{s.intensity}%</span>
                      </span>
                    </td>
                    <td className="timecode px-3 py-3">{duration(s.durationS * 1000)}</td>
                    <td className="timecode px-3 py-3 text-muted-foreground">{s.createdAt}</td>
                    <td className="px-3 py-3">
                      <StatusPill tone={s.status === "Interrupted" ? "live" : s.status === "Exported" ? "success" : "muted"}>{s.status}</StatusPill>
                    </td>
                    <td className="px-3 py-3 text-right" onClick={(ev) => ev.stopPropagation()}>
                      <Button variant="ghost" size="icon" aria-label={`Export ${s.name}`} onClick={exportSoon}><Download /></Button>
                      <Button variant="ghost" size="icon" aria-label={`Delete ${s.name}`} onClick={() => setConfirm(s)}><Trash2 /></Button>
                    </td>
                  </tr>
                );
              })}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-10 text-center text-sm text-muted-foreground">No sessions match these filters.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">{filtered.length} of {rows.length} demonstration records · deleting here only changes this preview.</p>
      </section>

      <Sheet open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-md">
          {detail && (
            <>
              <SheetHeader>
                <DemoNote />
                <SheetTitle className="font-display text-3xl font-normal">{detail.name}</SheetTitle>
                <SheetDescription>{detail.avatar} · {detail.createdAt}</SheetDescription>
              </SheetHeader>
              <div className="stage mt-6 rounded-lg p-3">
                <FrameStrip frames={4} start={60} emotion={detail.emotion} intensity={detail.intensity} />
                <p className="eyebrow mt-3 text-[9px] text-stage-muted">Video preview unavailable · demonstration record</p>
              </div>
              <dl className="mt-6 divide-y divide-border border-y border-border text-sm">
                {([
                  ["Input source", detail.input],
                  ["Emotion", `${emotionById(detail.emotion).label} · ${detail.intensity}%`],
                  ["Duration", duration(detail.durationS * 1000)],
                  ["Status", detail.status],
                  ["Output", "512×512 · AI watermark"],
                ] as [string, string][]).map(([k, v]) => (
                  <div key={k} className="flex justify-between py-2.5">
                    <dt className="text-muted-foreground">{k}</dt>
                    <dd className="font-medium">{v}</dd>
                  </div>
                ))}
              </dl>
              <div className="mt-6 flex gap-2">
                <Button variant="ink" onClick={exportSoon}><Download /> Export</Button>
                <Button variant="ghost" className="text-destructive" onClick={() => { setConfirm(detail); }}><Trash2 /> Delete</Button>
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>

      <AlertDialog open={!!confirm} onOpenChange={(o) => !o && setConfirm(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete “{confirm?.name}”?</AlertDialogTitle>
            <AlertDialogDescription>This is a demonstration record, so it's only removed from this preview.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => {
                setRows((r) => r.filter((x) => x.id !== confirm?.id));
                if (detail?.id === confirm?.id) setDetail(null);
              }}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Page>
  );
}
