import type { SyncStatus } from "@stockpilot/contract";
import { useQuery } from "@tanstack/react-query";

export const syncQuery = {
  queryKey: ["sync"],
  queryFn: async (): Promise<SyncStatus> => {
    const res = await fetch("/api/sync");
    if (!res.ok) throw new Error(`GET /api/sync failed: ${res.status}`);
    return (await res.json()) as SyncStatus;
  },
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** "28 Nov, 09:15" from an IST time text; the owners read IST, so no zone maths. */
export function shortTime(ist: string | null | undefined): string | undefined {
  const m = /^\d{4}-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(ist ?? "");
  if (!m) return undefined;
  return `${Number(m[2])} ${MONTHS[Number(m[1]) - 1]}, ${m[3]}:${m[4]}`;
}

/** The shell's "Kite synced at" time, or undefined before the first Sync. */
export function useSyncedAt(): string | undefined {
  const q = useQuery({ ...syncQuery, staleTime: 60_000 });
  return shortTime(q.data?.synced_at);
}
