import type { AdminOverview, AdminState } from "@stockpilot/contract";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { Pane } from "../../areas";
import { useWords } from "../../words";

async function send(method: string, url: string, body?: unknown): Promise<Response> {
  const res = await fetch(url, {
    method,
    headers: { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${method} ${url} failed: ${res.status}`);
  return res;
}

const overviewQuery = {
  queryKey: ["admin"],
  queryFn: async () => (await (await send("GET", "/api/admin")).json()) as AdminOverview,
};
const stateQuery = {
  queryKey: ["admin", "state"],
  queryFn: async () => (await (await send("GET", "/api/admin/state")).json()) as AdminState,
};

export function AdminPane() {
  const t = useWords();
  const qc = useQueryClient();
  const overview = useQuery(overviewQuery);
  const state = useQuery(stateQuery);
  const refresh = () => qc.invalidateQueries({ queryKey: ["admin"] });
  const retry = useMutation({
    mutationFn: (key: string) => send("POST", "/api/admin/retry", { key }),
    onSuccess: refresh,
  });
  const releasePause = useMutation({
    mutationFn: (paused: boolean) => send("PUT", "/api/admin/release-pause", { paused }),
    onSuccess: refresh,
  });
  const kindPause = useMutation({
    mutationFn: (v: { kind: string; paused: boolean }) => send("PUT", "/api/admin/job-pause", v),
    onSuccess: refresh,
  });
  const recompute = useMutation({
    mutationFn: (v: { dataset: string; days: number }) => send("POST", "/api/admin/recompute", v),
    onSuccess: refresh,
  });
  const [dataset, setDataset] = useState("");
  const [days, setDays] = useState(7);

  if (overview.isError) return <p role="alert">{t("admin.failed")}</p>;
  const o = overview.data;
  const s = state.data;
  const kinds = o ? [...new Set(o.freshness.map((f) => f.job))] : [];
  return (
    <section>
      <h1>{t("admin.title")}</h1>

      <h2>{t("admin.needs")}</h2>
      {o && o.needs_you.length === 0 && <p>{t("admin.needs.none")}</p>}
      <ul data-testid="needs">
        {o?.needs_you.map((n) => (
          <li key={n.id}>{n.url ? <a href={n.url}>{n.text}</a> : n.text}</li>
        ))}
      </ul>

      <h2>{t("admin.switches")}</h2>
      <label>
        <input
          type="checkbox"
          data-testid="release-pause"
          checked={s?.release_paused ?? false}
          disabled={!s || releasePause.isPending}
          onChange={(e) => releasePause.mutate(e.target.checked)}
        />{" "}
        {t("admin.release.pause")}
      </label>
      <ul data-testid="kinds">
        {kinds.map((k) => (
          <li key={k}>
            <label>
              <input
                type="checkbox"
                checked={s?.paused_kinds.includes(k as never) ?? false}
                disabled={!s || kindPause.isPending}
                onChange={(e) => kindPause.mutate({ kind: k, paused: e.target.checked })}
              />{" "}
              {t("admin.kind.pause")} {k}
            </label>
          </li>
        ))}
      </ul>

      <h2>{t("admin.recompute")}</h2>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (dataset) recompute.mutate({ dataset, days });
        }}
      >
        <label>
          {t("admin.recompute.dataset")}{" "}
          <select value={dataset} onChange={(e) => setDataset(e.target.value)}>
            <option value="" />
            {o?.freshness.map((f) => (
              <option key={f.dataset} value={f.dataset}>
                {f.dataset}
              </option>
            ))}
          </select>
        </label>{" "}
        <label>
          {t("admin.recompute.days")}{" "}
          <input
            type="number"
            min={1}
            max={366}
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
          />
        </label>{" "}
        <button type="submit" disabled={!dataset || recompute.isPending}>
          {t("admin.recompute.press")}
        </button>
      </form>
      {recompute.isSuccess && <output>{t("admin.recompute.queued")}</output>}
      {recompute.isError && <p role="alert">{t("admin.recompute.failed")}</p>}

      <h2>{t("admin.freshness")}</h2>
      <ul data-testid="freshness">
        {o?.freshness.map((f) => (
          <li key={f.dataset} data-state={f.state}>
            {f.dataset}: {t(`admin.state.${f.state}`)}
          </li>
        ))}
      </ul>

      <h2>{t("admin.runs")}</h2>
      {o && o.runs.length === 0 && <p>{t("admin.runs.none")}</p>}
      <ul data-testid="runs">
        {o?.runs.map((r) => (
          <li key={r.key} data-status={r.status}>
            {r.kind} {r.day}: {r.status}
            {r.error ? ` (${r.error})` : ""}
            <ol>
              {r.trail.map((step, i) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: a trail is append-only text
                <li key={i}>{step.text}</li>
              ))}
            </ol>
            {r.status === "failed" && (
              <button type="button" disabled={retry.isPending} onClick={() => retry.mutate(r.key)}>
                {retry.isPending ? t("admin.retrying") : t("admin.retry")}
              </button>
            )}
          </li>
        ))}
      </ul>
      {retry.isError && <p role="alert">{t("admin.retry.failed")}</p>}

      <h2>{t("admin.problems")}</h2>
      {o && o.problems.length === 0 && <p>{t("admin.problems.none")}</p>}
      <ul data-testid="problems">
        {o?.problems.map((p) => (
          <li key={p.id}>
            {p.at} {p.pane ? `[${p.pane}] ` : ""}
            {p.message}
          </li>
        ))}
      </ul>

      <h2>{t("admin.usage")}</h2>
      {o && o.usage.length === 0 && <p>{t("admin.usage.none")}</p>}
      <ul data-testid="usage">
        {o?.usage.map((u) => (
          <li key={`${u.screen}/${u.button}`}>
            {u.screen}
            {u.button ? ` / ${u.button}` : ""}: {u.n}
          </li>
        ))}
      </ul>
    </section>
  );
}

const pane: Pane = { id: "admin", path: "/admin", titleKey: "admin.title", Component: AdminPane };
export default pane;
