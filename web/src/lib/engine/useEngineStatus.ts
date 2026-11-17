import { useQuery } from "@tanstack/react-query";
import { useSettings } from "../settings";
import { fetchEngineInfo } from "./client";

export function useEngineStatus() {
  const engineUrl = useSettings((s) => s.engineUrl);
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
  return { engineUrl, status, info: q.data, refetch: q.refetch };
}
