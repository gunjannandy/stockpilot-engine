import type { AdminOverview } from "@stockpilot/contract";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { Pane as PaneDef } from "../../areas";
import { Pane } from "../../panekit";
import { useWords } from "../../words";

type Overview = AdminOverview;

async function sendUsage(button: string) {
  try {
    await fetch("/api/usage", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ screen: "admin", button }),
    });
  } catch {
    // Counting must never break a click.
  }
}

function TryAgain({ runKey }: { runKey: string }) {
  const t = useWords();
  const qc = useQueryClient();
  const retry = useMutation({
    mutationFn: async () => {
      void sendUsage("try-again");
      const r = await fetch("/api/admin/retry", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ key: runKey }),
      });
      if (!r.ok) throw new Error("retry failed");
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pane", "/api/admin"] }),
  });
  return (
    <button type="button" disabled={retry.isPending} onClick={() => retry.mutate()}>
      {t("admin.retry")}
    </button>
  );
}

const hhmm = (at: string | null) => (at ? at.replace("T", " ").slice(5, 16) : "");

export function AdminPane() {
  const t = useWords();
  return (
    <Pane<Overview>
      id="admin"
      title={t("admin.title")}
      path="/api/admin"
      windowHours={1}
      updatedAt={(d) => d.at}
    >
      {(d) => (
        <div className="admin">
          <h3>{t("admin.needs")}</h3>
          {d.needs_you.length === 0 ? (
            <p data-testid="admin-nothing">{t("admin.nothing")}</p>
          ) : (
            <ul data-testid="admin-needs">
              {d.needs_you.map((n) => (
                <li key={n.id}>{n.text}</li>
              ))}
            </ul>
          )}

          <h3>{t("admin.fresh")}</h3>
          <ul data-testid="admin-fresh">
            {d.freshness.map((f) => (
              <li key={f.dataset}>
                <strong>{f.dataset}</strong> · {f.schedule} ·{" "}
                <span className={`chip fresh ${f.state === "fresh" ? "ok" : "stale"}`}>
                  {f.updated_at ? `${t("admin.updated")} ${hhmm(f.updated_at)}` : t("admin.never")}
                </span>
              </li>
            ))}
          </ul>

          <h3>{t("admin.runs")}</h3>
          <ul data-testid="admin-runs">
            {d.runs.map((r) => (
              <li key={r.key}>
                <strong>{r.kind}</strong> · {r.day} · {r.status}
                {r.error ? ` · ${r.error}` : ""}
                <details>
                  <summary>{r.trail.length} steps</summary>
                  <ol>
                    {r.trail.map((s) => (
                      <li key={`${s.text}-${s.at}`}>
                        {hhmm(s.at)} {s.text}
                      </li>
                    ))}
                  </ol>
                </details>
                {r.status === "failed" ? <TryAgain runKey={r.key} /> : null}
              </li>
            ))}
          </ul>

          <h3>{t("admin.problems")}</h3>
          {d.problems.length === 0 ? (
            <p>{t("admin.noproblems")}</p>
          ) : (
            <ul data-testid="admin-problems">
              {d.problems.map((p) => (
                <li key={p.id}>
                  {hhmm(p.at)} · {p.pane ?? p.url ?? ""} · {p.message}
                </li>
              ))}
            </ul>
          )}

          <h3>{t("admin.usage")}</h3>
          {d.usage.length === 0 ? (
            <p>{t("admin.nousage")}</p>
          ) : (
            <ul data-testid="admin-usage">
              {d.usage.map((u) => (
                <li key={`${u.screen}-${u.button}`}>
                  {u.screen}
                  {u.button ? ` / ${u.button}` : ""}: {u.n}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Pane>
  );
}

const pane: PaneDef = {
  id: "admin",
  path: "/admin",
  titleKey: "admin.title",
  Component: AdminPane,
};
export default pane;
