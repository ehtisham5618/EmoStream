import { useEffect } from "react";
import { toast } from "sonner";

/**
 * A page left open (or cached) from an earlier deployment must not talk to a newer engine:
 * if the server bundles a different build of this page, reload once to pick it up.
 * Only applies when the page is served by the engine itself (same origin).
 */
export function BuildCheck() {
  useEffect(() => {
    if (typeof __BUILD__ !== "string") return;
    let cancelled = false;
    fetch("/api/info", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((info: { frontend_build?: string | null } | null) => {
        const server = info?.frontend_build;
        if (cancelled || !server || server === __BUILD__) return;
        let tried = false;
        try {
          tried = sessionStorage.getItem("emostream-reloaded") === server;
        } catch {
          /* storage unavailable */
        }
        if (!tried) {
          try {
            sessionStorage.setItem("emostream-reloaded", server);
          } catch {
            /* storage unavailable */
          }
          window.location.reload();
          return;
        }
        toast.error("This page is out of date", { description: "Reload it (Ctrl+Shift+R) before starting a session.", duration: Infinity });
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);
  return null;
}
