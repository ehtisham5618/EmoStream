import { useQuery } from "@tanstack/react-query";
import { useSettings } from "../settings";
import { engineBase, fetchEngineInfo } from "./client";

/** Engine reachability from GET /api/info. The engine is the page's own origin unless configured. */
export function useEngineStatus() {
  const configured = useSettings((s) => s.engineUrl);
  const engineUrl = engineBase(configured);
  const q = useQuery({
    queryKey: ["engine-info", engineUrl],
    queryFn: ({ signal }) => fetchEngineInfo(engineUrl, signal),
    enabled: !!engineUrl,
    refetchInterval: 20000,
    retry: false,
  });
  const status: "unset" | "checking" | "online" | "offline" = !engineUrl
    ? "unset"
    : q.isPending
      ? "checking"
      : q.data?.ok
        ? "online"
        : "offline";
  return { engineUrl, configured, status, info: q.data, refetch: q.refetch };
}
