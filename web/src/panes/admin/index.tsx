import "./admin.css";
import type { AdminOverview } from "@stockpilot/contract";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { Pane as PaneDef } from "../../areas";
import { Pane } from "../../panekit";
import { useWords } from "../../words";
import { Group, GroupNav } from "../_kit/ui";
import { Controls } from "../adminctl/Controls";

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

const STATUS_TONE: Record<string, string> = {
  done: "ok",
  running: "go",
  queued: "wait",
  failed: "bad",
};

function AdminPane() {
  const t = useWords();
  return (
    <div className="admin">
      <header className="k-head">
        <p className="k-eyebrow">{t("shell.nav.admin")}</p>
        <h1>{t("admin.headline")}</h1>
        <p>{t("admin.sub")}</p>
      </header>
      <GroupNav
        label={t("v3.groupsNav")}
        items={[
          { id: "needs", label: t("admin.needs") },
          { id: "fresh", label: t("admin.freshS") },
          { id: "runs", label: t("admin.runs") },
          { id: "problems", label: t("admin.problems") },
          { id: "usage", label: t("admin.usage") },
          { id: "controls", label: t("admin.controls") },
        ]}
      />
      <Pane<Overview>
        id="admin"
        title={t("admin.title")}
        path="/api/admin"
        windowHours={1}
        updatedAt={(d) => d.at}
      >
        {(d) => {
          const fresh = d.freshness.filter((f) => f.state === "fresh").length;
          const failed = d.runs.filter((r) => r.status === "failed").length;
          const top = Math.max(1, ...d.usage.map((u) => u.n));
          return (
            <>
              <div className="wl-glance">
                {[
                  [t("admin.needs"), String(d.needs_you.length), d.needs_you.length ? "dn" : "up"],
                  [
                    t("admin.freshS"),
                    `${fresh}/${d.freshness.length}`,
                    fresh === d.freshness.length ? "up" : "dn",
                  ],
                  [t("admin.failedRuns"), String(failed), failed ? "dn" : "up"],
                  [t("admin.problems"), String(d.problems.length), d.problems.length ? "dn" : "up"],
                ].map(([k, v, tone], i) => (
                  <div key={k} className="wl-g" style={{ animationDelay: `${i * 60}ms` }}>
                    <span className="k-eyebrow">{k}</span>
                    <b className={`num ${tone}`}>{v}</b>
                  </div>
                ))}
              </div>

              <Group id="needs" title={t("admin.needs")} sub={t("admin.needsP")}>
                {d.needs_you.length === 0 ? (
                  <p className="ad-ok" data-testid="admin-nothing">
                    {t("admin.nothing")}
                  </p>
                ) : (
                  <ul className="ad-list" data-testid="admin-needs">
                    {d.needs_you.map((n) => (
                      <li key={n.id} className="ad-need">
                        <span className="ad-kind">{n.kind}</span>
                        <span>{n.text}</span>
                        {n.url ? (
                          <a href={n.url} target="_blank" rel="noreferrer">
                            {t("admin.open")}
                          </a>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                )}
              </Group>

              <Group id="fresh" title={t("admin.fresh")} sub={t("admin.freshP")}>
                <ul className="ad-cards" data-testid="admin-fresh">
                  {d.freshness.map((f) => (
                    <li key={f.dataset} className={`ad-card st-${f.state}`}>
                      <b>{f.dataset}</b>
                      <span className={`chip fresh ${f.state === "fresh" ? "ok" : "stale"}`}>
                        {f.updated_at
                          ? `${t("admin.updated")} ${hhmm(f.updated_at)}`
                          : t("admin.never")}
                      </span>
                      <span className="k-note">{f.schedule}</span>
                    </li>
                  ))}
                </ul>
              </Group>

              <Group id="runs" title={t("admin.runs")} sub={t("admin.runsP")}>
                <ul className="ad-list" data-testid="admin-runs">
                  {d.runs.map((r) => (
                    <li key={r.key} className={`ad-run st-${r.status}`}>
                      <div className="ad-run-h">
                        <span className={`ad-st ${STATUS_TONE[r.status] ?? ""}`}>{r.status}</span>
                        <strong>{r.kind}</strong>
                        <span className="k-note">{r.day}</span>
                        {r.status === "failed" ? <TryAgain runKey={r.key} /> : null}
                      </div>
                      {r.error ? <p className="ad-err">{r.error}</p> : null}
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
                    </li>
                  ))}
                </ul>
              </Group>

              <Group id="problems" title={t("admin.problems")} sub={t("admin.problemsP")}>
                {d.problems.length === 0 ? (
                  <p className="ad-ok">{t("admin.noproblems")}</p>
                ) : (
                  <ul className="ad-list" data-testid="admin-problems">
                    {d.problems.map((p) => (
                      <li key={p.id} className="ad-prob">
                        <span className="k-note num">{hhmm(p.at)}</span>
                        <b>{p.pane ?? p.url ?? ""}</b>
                        <span>{p.message}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </Group>

              <Group id="usage" title={t("admin.usage")} sub={t("admin.usageP")}>
                {d.usage.length === 0 ? (
                  <p className="k-note">{t("admin.nousage")}</p>
                ) : (
                  <ul className="ad-usage" data-testid="admin-usage">
                    {d.usage.map((u) => (
                      <li key={`${u.screen}-${u.button}`}>
                        <span>
                          {u.screen}
                          {u.button ? ` / ${u.button}` : ""}
                        </span>
                        <span className="k-bar-h">
                          <i className="k-grow" style={{ width: `${(u.n / top) * 100}%` }} />
                        </span>
                        <b className="num">{u.n}</b>
                      </li>
                    ))}
                  </ul>
                )}
              </Group>
            </>
          );
        }}
      </Pane>
      <Group id="controls" title={t("admin.controls")} sub={t("admin.controlsP")}>
        <Controls />
      </Group>
    </div>
  );
}

const pane: PaneDef = {
  id: "admin",
  path: "/admin",
  titleKey: "admin.title",
  Component: AdminPane,
};
export default pane;
