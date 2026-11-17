import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { SoonBadge } from "./Status";

interface SoonInfo {
  title: string;
  body: ReactNode;
  flow?: string[];
}

const Ctx = createContext<(info: SoonInfo) => void>(() => {});

/** Planned features open this explanation instead of a fake workflow. */
export function ComingSoonProvider({ children }: { children: ReactNode }) {
  const [info, setInfo] = useState<SoonInfo | null>(null);
  const open = useCallback((i: SoonInfo) => setInfo(i), []);
  return (
    <Ctx.Provider value={open}>
      {children}
      <Dialog open={!!info} onOpenChange={(o) => !o && setInfo(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <div className="mb-2">
              <SoonBadge />
            </div>
            <DialogTitle className="font-display text-3xl font-normal">{info?.title}</DialogTitle>
            <DialogDescription asChild>
              <div className="text-[15px] leading-relaxed">{info?.body}</div>
            </DialogDescription>
          </DialogHeader>
          {info?.flow && (
            <ol className="flex flex-wrap items-center gap-1.5">
              {info.flow.map((f, i) => (
                <li key={f} className="flex items-center gap-1.5">
                  <span className="timecode rounded border border-border bg-muted/60 px-2 py-1 text-[10.5px] uppercase">{f}</span>
                  {i < info.flow!.length - 1 && <span className="text-muted-foreground">→</span>}
                </li>
              ))}
            </ol>
          )}
          <DialogFooter>
            <Button variant="ink" onClick={() => setInfo(null)}>
              Understood
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Ctx.Provider>
  );
}

export const useComingSoon = () => useContext(Ctx);
