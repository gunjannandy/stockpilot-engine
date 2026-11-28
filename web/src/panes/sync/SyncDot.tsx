import { useQuery } from "@tanstack/react-query";
import { useWords } from "../../words";
import "./sync.css";
import { syncQuery } from "./useSynced";

/** The yellow dot on the Sync control: the Worker decides (trading day, last sync before 09:15 IST). */
export function SyncDot() {
  const t = useWords();
  const q = useQuery({ ...syncQuery, retry: false, staleTime: 60_000 });
  if (!q.data?.sync_dot) return null;
  return <span className="sync-dot" role="img" aria-label={t("sync.dot")} data-testid="sync-dot" />;
}
