import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Pane } from "../../areas";
import { useWords } from "../../words";
import { shortTime, syncQuery } from "./useSynced";

export function SyncPane() {
  const t = useWords();
  const qc = useQueryClient();
  const status = useQuery(syncQuery);
  const refresh = useMutation({
    mutationFn: async () => {
      const res = await fetch("/api/refresh", { method: "POST" });
      if (!res.ok) throw new Error(String(res.status));
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sync"] }),
  });
  const data = status.data;
  return (
    <section>
      <h1>{t("sync.title")}</h1>
      <p>
        <a className="button" href="/kite/login" data-testid="sync-button">
          {t("sync.press")}
        </a>
      </p>
      <p>
        {t("sync.last")}:{" "}
        <span data-testid="synced-at">{shortTime(data?.synced_at) ?? t("sync.never")}</span>
      </p>
      {data && data.steps.length > 0 && (
        <ol data-testid="steps">
          {data.steps.map((s) => (
            <li key={s.id} data-state={s.state}>
              {s.id === "done"
                ? `${t("sync.step.done")}, ${s.count ?? 0} ${t(s.count === 1 ? "sync.change" : "sync.changes")}`
                : `${t(`sync.step.${s.id}`)}${s.count === null ? "" : `: ${s.count}`}`}
            </li>
          ))}
        </ol>
      )}
      <h2>{t("sync.refresh.title")}</h2>
      <p>{t("sync.refresh.about")}</p>
      <button type="button" disabled={refresh.isPending} onClick={() => refresh.mutate()}>
        {refresh.isPending ? t("sync.refresh.pressing") : t("sync.refresh.press")}
      </button>
      {refresh.isSuccess && <output>{t("sync.refresh.started")}</output>}
      {refresh.isError && <p role="alert">{t("sync.refresh.failed")}</p>}
    </section>
  );
}

const pane: Pane = { id: "sync", path: "/sync", titleKey: "sync.title", Component: SyncPane };
export default pane;
