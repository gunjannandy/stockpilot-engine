import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Pane } from "../../areas";
import { createClient } from "../../generated/client";
import { useWords } from "../../words";

const client = createClient();

export function PingPane() {
  const t = useWords();
  const qc = useQueryClient();
  const latest = useQuery({ queryKey: ["ping"], queryFn: () => client.pingLatest() });
  const press = useMutation({
    mutationFn: () => client.pingPress(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ping"] }),
  });
  return (
    <section>
      <h1>{t("ping.title")}</h1>
      <button type="button" disabled={press.isPending} onClick={() => press.mutate()}>
        {press.isPending ? t("ping.pressing") : t("ping.press")}
      </button>
      {press.isError && <p role="alert">{t("ping.failed")}</p>}
      <p>
        {t("ping.last")}:{" "}
        <span data-testid="last">{latest.data?.latest?.at ?? t("ping.never")}</span>
      </p>
      <p>
        {t("ping.count")}: <span data-testid="count">{latest.data?.count ?? 0}</span>
      </p>
    </section>
  );
}

const pane: Pane = { id: "ping", path: "/ping", titleKey: "ping.title", Component: PingPane };
export default pane;
