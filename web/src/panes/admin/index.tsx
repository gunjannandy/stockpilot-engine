// Admin: the console both owners open, and the same glance the morning email will show.
// Glance: what needs you, what is running now, the asks being worked on (they follow their GitHub tickets),
// and one card per job kind with Run now, Re-run and Pause. Details: the filterable lists behind it.
import "./admin.css";
import {
  type AdminOverview,
  type AdminState,
  datasets,
  type FeedbackAsk,
  FeedbackList,
  JobKind,
} from "@stockpilot/contract";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { Pane as PaneDef } from "../../areas";
import { useWords } from "../../words";
import { Toast } from "../_kit/Toast";
import { Seg } from "../_kit/ui";
import { watch } from "../_kit/watch";
import { Screens } from "./Screens";

type Run = AdminOverview["runs"][number];
type Fresh = AdminOverview["freshness"][number];
type Monitor = Record<string, number | string>;

async function call<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const r = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) {
    const j = (await r.json().catch(() => null)) as { error?: string } | null;
    throw new Error(j?.error ?? `HTTP ${r.status}`);
  }
  return (await r.json()) as T;
}

/** Where an ask's ticket lives (the same repo the API's ticket follower reads). */
const TICKET_REPO = "stockpilot-hq/stockpilot";
/** Kinds that are plumbing, not work the owners think about. */
const QUIET = new Set(["ping", "drill"]);
const DS = Object.values(datasets) as { name: string; job: string; recomputable: boolean }[];
const recomputable = (kind: string) => DS.find((d) => d.job === kind && d.recomputable)?.name;
const hhmm = (at: string | null | undefined) => (at ? at.replace("T", " ").slice(11, 16) : "");
const dayTime = (at: string | null | undefined) =>
  at ? `${at.slice(8, 10)}/${at.slice(5, 7)} ${at.slice(11, 16)}` : "";
const ago = (at: string | null | undefined, now: string) => {
  if (!at) return null;
  const m = Math.round((Date.parse(now) - Date.parse(at)) / 60000);
  return m < 60
    ? `${Math.max(1, m)}m`
    : m < 2880
      ? `${Math.round(m / 60)}h`
      : `${Math.round(m / 1440)}d`;
};
const took = (r: Run) =>
  r.started_at && r.finished_at
    ? Math.max(1, Math.round((Date.parse(r.finished_at) - Date.parse(r.started_at)) / 60000))
    : null;

function useAdmin() {
  const qc = useQueryClient();
  const again = () => {
    qc.invalidateQueries({ queryKey: ["admin"] });
    qc.invalidateQueries({ queryKey: ["admin-state"] });
    qc.invalidateQueries({ queryKey: ["feedback"] });
  };
  return {
    overview: useQuery({
      queryKey: ["admin"],
      queryFn: () => call<AdminOverview>("/api/admin"),
      refetchInterval: 15_000,
    }),
    state: useQuery({
      queryKey: ["admin-state"],
      queryFn: () => call<AdminState>("/api/admin/state"),
      retry: false,
    }),
    asks: useQuery({
      queryKey: ["feedback"],
      queryFn: async () => FeedbackList.parse(await call("/api/feedback")),
      refetchInterval: 30_000,
      retry: false,
    }),
    monitor: useQuery({
      queryKey: ["monitor"],
      queryFn: () => call<Monitor>("/api/monitor"),
      retry: false,
    }),
    again,
  };
}

/* ---------- Glance ---------- */

function Needs({ d }: { d: AdminOverview }) {
  const t = useWords();
  const stale = d.freshness.filter((f) => f.state !== "fresh");
  if (!d.needs_you.length && !stale.length)
    return (
      <p className="ad-allok k-up" data-testid="admin-nothing">
        <i /> {t("admin.nothing")}
      </p>
    );
  return (
    <ul className="ad-needs" data-testid="admin-needs">
      {d.needs_you.map((n, i) => (
        <li key={n.id} className="ad-need k-up" style={{ "--i": i } as React.CSSProperties}>
          <span className="ad-tag">{n.kind}</span>
          <span>{n.text}</span>
          {n.url ? (
            <a className="k-link" href={n.url} target="_blank" rel="noreferrer">
              {t("admin.open")}
            </a>
          ) : null}
        </li>
      ))}
      {stale.map((f, i) => (
        <li
          key={f.dataset}
          className="ad-need k-up"
          style={{ "--i": d.needs_you.length + i } as React.CSSProperties}
        >
          <span className="ad-tag">{t("console.stale")}</span>
          <span>
            {f.state === "never"
              ? t("console.neverLine").replace("{d}", f.dataset)
              : t("console.staleLine")
                  .replace("{d}", f.dataset)
                  .replace("{a}", ago(f.updated_at, d.at) ?? "")}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** A running job: its steps so far, the one in hand, and a bar that moves while it works. */
function RunningCard({ r, now }: { r: Run; now: string }) {
  const t = useWords();
  const steps = r.trail.slice(-5);
  return (
    <article className="ad-live card k-up" data-testid="admin-running">
      <header>
        <b>{t(`console.kind.${r.kind}`)}</b>
        <span className={`ad-st ${r.status}`}>{t(`console.st.${r.status}`)}</span>
      </header>
      <ol className="ad-steps">
        {steps.map((s, i) => (
          <li key={`${s.at}-${s.text}`} className={i === steps.length - 1 ? "now" : "done"}>
            <i />
            <span>{s.text}</span>
          </li>
        ))}
        {steps.length === 0 ? (
          <li className="now">
            <i />
            <span>{t("console.waiting")}</span>
          </li>
        ) : null}
      </ol>
      <span className="ad-work" aria-hidden="true">
        <i />
      </span>
      <p className="k-note">
        {r.started_at
          ? t("console.startedAgo").replace("{a}", ago(r.started_at, now) ?? "")
          : t("console.queued")}
        {r.attempts > 1 ? ` · ${t("console.attempt").replace("{n}", String(r.attempts))}` : ""}
      </p>
    </article>
  );
}

function Running({ d }: { d: AdminOverview }) {
  const t = useWords();
  const live = d.runs.filter((r) => r.status === "running" || r.status === "queued");
  const last = d.runs.find((r) => r.status === "done");
  return (
    <section className="ad-sec">
      <h2 className="ad-h">
        {t("console.running")} <span className="num">{live.length}</span>
      </h2>
      {live.length ? (
        <div className="ad-livegrid">
          {live.map((r) => (
            <RunningCard key={r.key} r={r} now={d.at} />
          ))}
        </div>
      ) : (
        <p className="k-note">
          {last
            ? t("console.idleLast")
                .replace("{k}", t(`console.kind.${last.kind}`))
                .replace("{t}", hhmm(last.finished_at))
            : t("console.idle")}
        </p>
      )}
    </section>
  );
}

const COLS = [
  { id: "new", st: ["received"] },
  { id: "planned", st: ["reviewed", "planned"] },
  { id: "building", st: ["being_built"] },
  { id: "done", st: ["done"] },
] as const;

/** An ask on the board. New ones carry the owner's review: what we understood, Plan or Not planned. */
function AskCard({ a, owner, i }: { a: FeedbackAsk; owner: boolean; i: number }) {
  const t = useWords();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [u, setU] = useState(a.understanding ?? "");
  const save = useMutation({
    mutationFn: (decision: "reviewed" | "not_planned") =>
      call(`/api/feedback/${a.id}/review`, "POST", { understanding: u, decision }),
    onSuccess: () => {
      watch.say(t("console.reviewed"));
      return qc.invalidateQueries({ queryKey: ["feedback"] });
    },
    onError: (e) => watch.say(String((e as Error).message)),
  });
  return (
    <li className="ad-ask k-up k-lift" style={{ "--i": i } as React.CSSProperties}>
      <p className="ad-ask-t">{a.text}</p>
      {a.understanding ? <p className="k-note">↳ {a.understanding}</p> : null}
      <footer>
        <span className="k-note num">{dayTime(a.created_at)}</span>
        {a.job ? (
          <a
            className="ad-ticket num"
            href={`https://github.com/${TICKET_REPO}/issues/${a.job}`}
            target="_blank"
            rel="noreferrer"
          >
            #{a.job}
          </a>
        ) : null}
        {owner && a.status === "received" && !open ? (
          <button type="button" className="k-link" onClick={() => setOpen(true)}>
            {t("console.review")}
          </button>
        ) : null}
      </footer>
      {open ? (
        <div className="ad-review k-in">
          <label className="sr" htmlFor={`u-${a.id}`}>
            {t("feedback.understanding")}
          </label>
          <textarea
            id={`u-${a.id}`}
            rows={2}
            value={u}
            placeholder={t("feedback.understanding")}
            onChange={(e) => setU(e.target.value)}
          />
          <div className="ad-acts">
            <button
              type="button"
              className="sk-btn sk-tonal"
              disabled={!u.trim() || save.isPending}
              onClick={() => save.mutate("reviewed")}
            >
              {t("console.plan")}
            </button>
            <button
              type="button"
              className="sk-btn"
              disabled={!u.trim() || save.isPending}
              onClick={() => save.mutate("not_planned")}
            >
              {t("feedback.status.not_planned")}
            </button>
          </div>
        </div>
      ) : null}
    </li>
  );
}

function Board({ asks, owner }: { asks: FeedbackAsk[]; owner: boolean }) {
  const t = useWords();
  const dropped = asks.filter((a) => a.status === "not_planned").length;
  return (
    <section className="ad-sec">
      <h2 className="ad-h">
        {t("console.asks")}
        {dropped ? (
          <span className="k-note">
            {" "}
            · {dropped} {t("feedback.status.not_planned").toLowerCase()}
          </span>
        ) : null}
      </h2>
      <div className="ad-board" data-testid="admin-board">
        {COLS.map((c) => {
          const list = asks.filter((a) => (c.st as readonly string[]).includes(a.status));
          return (
            <section key={c.id} className={`ad-col c-${c.id}`}>
              <h3>
                {t(`console.col.${c.id}`)} <span className="num">{list.length}</span>
              </h3>
              <ul>
                {list.map((a, i) => (
                  <AskCard key={a.id} a={a} owner={owner} i={i} />
                ))}
                {list.length === 0 ? <li className="ad-empty">–</li> : null}
              </ul>
            </section>
          );
        })}
      </div>
    </section>
  );
}

function JobCard({
  kind,
  run,
  fresh,
  paused,
  now,
  i,
  again,
}: {
  kind: string;
  run?: Run;
  fresh?: Fresh;
  paused: boolean;
  now: string;
  i: number;
  again: () => void;
}) {
  const t = useWords();
  const [days, setDays] = useState<number | null>(null);
  const ds = recomputable(kind);
  const act = useMutation({
    mutationFn: (what: "run" | "retry" | "pause" | "rerun") =>
      what === "run"
        ? call("/api/job/press", "POST", { kind, subject: "all" })
        : what === "retry"
          ? call("/api/admin/retry", "POST", { key: run?.key })
          : what === "pause"
            ? call("/api/admin/job-pause", "PUT", { kind, paused: !paused })
            : call("/api/admin/recompute", "POST", { dataset: ds, days }),
    onSuccess: (_d, what) => {
      watch.say(t(`console.did.${what}`));
      setDays(null);
      again();
    },
    onError: (e) => watch.say(String((e as Error).message)),
  });
  const state = paused
    ? "paused"
    : run?.status === "failed"
      ? "failed"
      : run?.status === "running" || run?.status === "queued"
        ? "running"
        : fresh && fresh.state !== "fresh"
          ? "stale"
          : run || fresh?.updated_at
            ? "ok"
            : "never";
  const mins = run ? took(run) : null;
  return (
    <article
      className={`ad-job card k-up s-${state}`}
      style={{ "--i": i } as React.CSSProperties}
      data-testid="admin-job"
    >
      <header>
        <i className="ad-dot" aria-hidden="true" />
        <b>{t(`console.kind.${kind}`)}</b>
        <span className="ad-jst">{t(`console.js.${state}`)}</span>
      </header>
      <dl>
        <div>
          <dt>{t("console.last")}</dt>
          <dd className="num">
            {run ? `${dayTime(run.finished_at ?? run.started_at) || run.day}` : "–"}
            {mins ? <span className="k-note"> · {mins}m</span> : null}
          </dd>
        </div>
        <div>
          <dt>{t("console.data")}</dt>
          <dd className="num">
            {fresh?.updated_at
              ? t("console.agoShort").replace("{a}", ago(fresh.updated_at, now) ?? "")
              : "–"}
          </dd>
        </div>
      </dl>
      {fresh?.schedule ? <p className="k-note ad-sched">{fresh.schedule}</p> : null}
      {run?.status === "failed" && run.error ? <p className="ad-err">{run.error}</p> : null}
      <div className="ad-acts">
        {run?.status === "failed" ? (
          <button
            type="button"
            className="sk-btn sk-tonal"
            disabled={act.isPending}
            onClick={() => act.mutate("retry")}
          >
            {t("admin.retry")}
          </button>
        ) : (
          <button
            type="button"
            className="sk-btn sk-tonal"
            disabled={act.isPending || paused || state === "running"}
            onClick={() => act.mutate("run")}
          >
            {t("console.runNow")}
          </button>
        )}
        {ds ? (
          <button
            type="button"
            className="sk-btn"
            onClick={() => setDays(days === null ? 7 : null)}
          >
            {t("console.rerun")}
          </button>
        ) : null}
        <button
          type="button"
          className="sk-btn ad-pause"
          aria-pressed={paused}
          disabled={act.isPending}
          onClick={() => act.mutate("pause")}
        >
          {paused ? t("console.resume") : t("console.pause")}
        </button>
      </div>
      {days !== null ? (
        <div className="ad-rerun k-in">
          <label>
            {t("console.lastDays")}
            <input
              className="k-input k-num"
              type="number"
              min={1}
              max={366}
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
            />
          </label>
          <button
            type="button"
            className="sk-btn sk-tonal"
            disabled={act.isPending || !(days >= 1)}
            onClick={() => act.mutate("rerun")}
          >
            {t("console.go")}
          </button>
        </div>
      ) : null}
    </article>
  );
}

function Jobs({
  d,
  state,
  again,
}: {
  d: AdminOverview;
  state: AdminState | undefined;
  again: () => void;
}) {
  const t = useWords();
  const kinds = JobKind.options.filter(
    (k) => !QUIET.has(k) || d.runs.some((r) => r.kind === k && r.status === "failed"),
  );
  const order = (k: string) => {
    const r = d.runs.find((x) => x.kind === k);
    return r?.status === "failed" ? 0 : r ? 1 : d.freshness.some((f) => f.job === k) ? 2 : 3;
  };
  const sorted = [...kinds].sort((a, b) => order(a) - order(b));
  const seen = (k: string) =>
    d.runs.some((r) => r.kind === k) ||
    d.freshness.some((f) => f.job === k) ||
    !!state?.paused_kinds.includes(k as JobKind);
  const cards = sorted.filter(seen);
  const quiet = sorted.filter((k) => !seen(k));
  return (
    <section className="ad-sec">
      <h2 className="ad-h">{t("console.jobs")}</h2>
      <div className="ad-jobs">
        {cards.map((k, i) => (
          <JobCard
            key={k}
            kind={k}
            i={i}
            run={d.runs.find((r) => r.kind === k)}
            fresh={d.freshness.find((f) => f.job === k)}
            paused={!!state?.paused_kinds.includes(k)}
            now={d.at}
            again={again}
          />
        ))}
      </div>
      {quiet.length ? (
        <div className="ad-quiet">
          <span className="k-note">{t("console.onDemand")}</span>
          {quiet.map((k) => (
            <QuietJob key={k} kind={k} again={again} />
          ))}
        </div>
      ) : null}
    </section>
  );
}

/** A kind that has not run yet: only its name and Run now. */
function QuietJob({ kind, again }: { kind: string; again: () => void }) {
  const t = useWords();
  const run = useMutation({
    mutationFn: () => call("/api/job/press", "POST", { kind, subject: "all" }),
    onSuccess: () => {
      watch.say(t("console.did.run"));
      again();
    },
    onError: (e) => watch.say(String((e as Error).message)),
  });
  return (
    <button
      type="button"
      className="ad-qjob"
      disabled={run.isPending}
      onClick={() => run.mutate()}
      title={t("console.runNow")}
    >
      {t(`console.kind.${kind}`)} <span aria-hidden="true">▶</span>
      <span className="sr">{t("console.runNow")}</span>
    </button>
  );
}

/* ---------- Details ---------- */

type DView = "runs" | "failed" | "problems" | "held" | "usage";
function Details({ d, monitor }: { d: AdminOverview; monitor: Monitor | undefined }) {
  const t = useWords();
  const [v, setV] = useState<DView>("runs");
  const [kind, setKind] = useState("all");
  const [ds, setDs] = useState(d.freshness[0]?.dataset ?? "");
  const held = useQuery({
    queryKey: ["held", ds],
    queryFn: () =>
      call<{ held: { run_id: string; seq: number; reason: string; body: string }[] }>(
        `/api/publish/held/${encodeURIComponent(ds)}`,
      ),
    enabled: v === "held" && !!ds,
    retry: false,
  });
  const runs = d.runs.filter(
    (r) => (v !== "failed" || r.status === "failed") && (kind === "all" || r.kind === kind),
  );
  const counts: Record<DView, number> = {
    runs: d.runs.length,
    failed: d.runs.filter((r) => r.status === "failed").length,
    problems: d.problems.length,
    held: held.data?.held.length ?? 0,
    usage: d.usage.length,
  };
  return (
    <section className="ad-details">
      <div className="k-bar">
        <div className="k-chips">
          {(["runs", "failed", "problems", "held", "usage"] as const).map((x) => (
            <button
              key={x}
              type="button"
              className="k-chipbtn"
              aria-pressed={v === x}
              onClick={() => setV(x)}
            >
              {t(`console.d.${x}`)}
              {x !== "held" ? <span className="num">{counts[x]}</span> : null}
            </button>
          ))}
        </div>
        {v === "runs" || v === "failed" ? (
          <select
            className="k-input"
            value={kind}
            onChange={(e) => setKind(e.target.value)}
            aria-label={t("console.kindFilter")}
          >
            <option value="all">{t("console.allKinds")}</option>
            {[...new Set(d.runs.map((r) => r.kind))].map((k) => (
              <option key={k} value={k}>
                {t(`console.kind.${k}`)}
              </option>
            ))}
          </select>
        ) : null}
        {v === "held" ? (
          <select
            className="k-input"
            value={ds}
            onChange={(e) => setDs(e.target.value)}
            aria-label={t("console.dataset")}
          >
            {d.freshness.map((f) => (
              <option key={f.dataset}>{f.dataset}</option>
            ))}
          </select>
        ) : null}
      </div>
      {v === "runs" || v === "failed" ? (
        <ul className="ad-dlist" data-testid="admin-runs">
          {runs.map((r) => (
            <li key={r.key} className={`ad-drow s-${r.status}`}>
              <details>
                <summary>
                  <span className={`ad-st ${r.status}`}>{t(`console.st.${r.status}`)}</span>
                  <b>{t(`console.kind.${r.kind}`)}</b>
                  <span className="k-note num">
                    {r.day} {hhmm(r.started_at)}
                  </span>
                  {took(r) ? <span className="k-note num">{took(r)}m</span> : null}
                  <span className="k-note">
                    {r.trail.length} {t("console.steps")}
                  </span>
                </summary>
                {r.error ? <p className="ad-err">{r.error}</p> : null}
                <ol className="ad-trail">
                  {r.trail.map((s) => (
                    <li key={`${s.text}-${s.at}`}>
                      <span className="num k-note">{hhmm(s.at)}</span> {s.text}
                    </li>
                  ))}
                </ol>
              </details>
            </li>
          ))}
          {runs.length === 0 ? <li className="k-note">{t("console.none")}</li> : null}
        </ul>
      ) : null}
      {v === "problems" ? (
        <ul className="ad-dlist" data-testid="admin-problems">
          {d.problems.map((p) => (
            <li key={p.id} className="ad-drow">
              <span className="k-note num">{dayTime(p.at)}</span> <b>{p.pane ?? p.url ?? ""}</b>{" "}
              {p.message}
            </li>
          ))}
          {d.problems.length === 0 ? <li className="k-note">{t("admin.noproblems")}</li> : null}
        </ul>
      ) : null}
      {v === "held" ? (
        <ul className="ad-dlist">
          {(held.data?.held ?? []).map((h) => (
            <li key={`${h.run_id}-${h.seq}`} className="ad-drow">
              <b>{h.reason}</b> <code className="k-note">{h.body.slice(0, 160)}</code>
            </li>
          ))}
          {held.data && held.data.held.length === 0 ? (
            <li className="k-note">{t("console.noHeld")}</li>
          ) : null}
          {held.isError ? <li className="k-note">{t("panes.failed")}</li> : null}
        </ul>
      ) : null}
      {v === "usage" ? (
        <div className="ad-usage" data-testid="admin-usage">
          {monitor ? (
            <p className="k-note">
              {["d1_reads", "d1_writes", "worker_requests", "build_minutes"]
                .filter((k) => k in monitor)
                .map((k) => `${t(`console.m.${k}`)} ${Number(monitor[k]).toLocaleString("en-IN")}`)
                .join(" · ")}
            </p>
          ) : null}
          <ul className="ad-dlist">
            {d.usage.map((u) => (
              <li key={`${u.screen}-${u.button}`} className="ad-drow">
                {u.screen}
                {u.button ? ` / ${u.button}` : ""} <b className="num">{u.n}</b>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

/* ---------- Screen ---------- */

function PauseReleases({ state, again }: { state: AdminState | undefined; again: () => void }) {
  const t = useWords();
  const on = !!state?.release_paused;
  const flip = useMutation({
    mutationFn: () => call("/api/admin/release-pause", "PUT", { paused: !on }),
    onSuccess: () => {
      watch.say(on ? t("v3.pausedOff") : t("v3.pausedOn"));
      again();
    },
    onError: (e) => watch.say(String((e as Error).message)),
  });
  return (
    <label className={`ad-release${on ? " on" : ""}`} title={t("console.releaseP")}>
      <span>
        <b>{on ? t("console.releasePaused") : t("console.releaseLive")}</b>
        <span className="k-note">{t("console.releaseP")}</span>
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={on}
        aria-label={t("v3.pauseRel")}
        className="ac-sw"
        disabled={!state || flip.isPending}
        onClick={() => flip.mutate()}
      >
        <i />
      </button>
    </label>
  );
}

function AdminPane() {
  const t = useWords();
  const a = useAdmin();
  const [view, setView] = useState<"glance" | "details">("glance");
  const d = a.overview.data;
  return (
    <section className="admin">
      <header className="ad-head">
        <div>
          <p className="k-eyebrow">{t("shell.nav.admin")}</p>
          <h1>{t("admin.headline")}</h1>
          {d ? <p className="k-note">{t("console.updated").replace("{t}", hhmm(d.at))}</p> : null}
        </div>
        <PauseReleases state={a.state.data} again={a.again} />
      </header>
      <div className="ad-view">
        <Seg
          label={t("console.view")}
          value={view}
          onChange={setView}
          options={[
            { id: "glance", label: t("console.glance") },
            { id: "details", label: t("console.details") },
          ]}
        />
      </div>
      {a.overview.isError ? (
        <div role="alert" className="pane-state failed" data-testid="admin-failed">
          <p>{t("panes.failed")}</p>
          <button type="button" className="sk-btn" onClick={() => a.overview.refetch()}>
            {t("panes.retry")}
          </button>
        </div>
      ) : null}
      {!d && !a.overview.isError ? <span className="k-skel ad-skel" /> : null}
      {d && view === "glance" ? (
        <div className="ad-glance">
          <Needs d={d} />
          <Running d={d} />
          {a.asks.data ? (
            <Board asks={a.asks.data.asks} owner={a.asks.data.person === "owner"} />
          ) : null}
          <Jobs d={d} state={a.state.data} again={a.again} />
          <Screens flags={a.state.data?.flags} again={a.again} />
        </div>
      ) : null}
      {d && view === "details" ? <Details d={d} monitor={a.monitor.data} /> : null}
      <Toast />
    </section>
  );
}

const pane: PaneDef = {
  id: "admin",
  path: "/admin",
  titleKey: "admin.title",
  Component: AdminPane,
};
export default pane;
