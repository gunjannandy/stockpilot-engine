// Portfolio: what we own and what to do with the month's money. One value line, a row of small cards
// (this month's plan, tax, RSUs, coming up), then one holdings table. The plan (budget, target mix) is edited here:
// there is no Settings screen. Made-up numbers throughout.
import type { SettingsResponse, TradesResponse } from "@stockpilot/contract";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { Pane } from "../../areas";
import { useWords } from "../../words";
import { callCard, HOLDINGS, lakh, money, pct } from "../_kit/data";
import { useCountUp } from "../_kit/hooks";
import { BUDGET, budgetFor, istMonth, MONEY_LEFT, spentIn, TARGET } from "../_kit/plan";
import { Toast } from "../_kit/Toast";
import { Seg, VChip } from "../_kit/ui";
import { watch } from "../_kit/watch";
import { shortTime, syncQuery } from "../sync/useSynced";
import "./portfolio.css";

type Scope = "all" | "kite" | "sc";
type Rows = typeof HOLDINGS;
const fill = (s: string, v: Record<string, string | number>) =>
  s.replace(/\{(\w+)\}/g, (_, k) => String(v[k] ?? ""));

/** This month: money left against the budget, the mix against the target, Kite. Budget and mix change in place. */
function Month({ rows }: { rows: Rows }) {
  const t = useWords();
  const sync = useQuery({ ...syncQuery, retry: false });
  const qc = useQueryClient();
  const settings = useQuery({
    queryKey: ["portfolio", "settings"],
    queryFn: async () => {
      const r = await fetch("/api/portfolio/settings");
      if (!r.ok) throw new Error(String(r.status));
      return (await r.json()) as SettingsResponse;
    },
    retry: false,
  });
  const trades = useQuery({
    queryKey: ["portfolio", "trades"],
    queryFn: async () => {
      const r = await fetch("/api/portfolio/trades");
      if (!r.ok) throw new Error(String(r.status));
      return (await r.json()) as TradesResponse;
    },
    retry: false,
  });
  const month = istMonth();
  const real = budgetFor(settings.data?.budget, month);
  // Real figures when the routes answer (owner only); the made-up ones stay while they do not.
  const [draft, setBudget] = useState<number | null>(null);
  const budget = draft ?? real ?? BUDGET;
  const MONEY_LEFT_NOW =
    trades.data && real !== null
      ? Math.max(0, real - spentIn(trades.data.trades, month))
      : MONEY_LEFT;
  const saveBudget = useMutation({
    mutationFn: async (v: number) => {
      const b = settings.data?.budget;
      const r = await fetch("/api/portfolio/budget", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          default: b?.default ?? v,
          months: { ...(b?.months ?? {}), [month]: v },
        }),
      });
      if (!r.ok) throw new Error(String(r.status));
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["portfolio"] }),
  });
  const [editB, setEditB] = useState(false);
  const [target, setTarget] = useState(TARGET);
  const [editM, setEditM] = useState(false);
  const left = useCountUp(MONEY_LEFT_NOW);
  const total = rows.reduce((a, r) => a + r.h.value, 0) || 1;
  const now = new Map<string, number>();
  for (const r of rows)
    now.set(r.st.sector, (now.get(r.st.sector) ?? 0) + (r.h.value / total) * 100);
  const sum = Object.values(target).reduce((a, b) => a + b, 0);
  const gaps = Object.entries(target)
    .map(([s, g]) => ({ s, g, v: now.get(s) ?? 0 }))
    .sort((a, b) => Math.abs(b.v - b.g) - Math.abs(a.v - a.g));
  return (
    <section className="card pf-month k-up">
      <header className="pf-ch">
        <h2>{t("pf.month")}</h2>
        <span className="k-note">
          {t("sync.last")}: {shortTime(sync.data?.synced_at) ?? t("sync.never")}
        </span>
        <a className="sk-btn" href="/kite/login" data-testid="sync-button">
          {t("sync.press")}
        </a>
      </header>
      <div className="pf-money">
        <div>
          <span className="k-eyebrow">{t("v2.tLeft")}</span>
          <b className="pf-big num">{money(Math.round(left), 0)}</b>
          <span className="k-bar-h gain" aria-hidden="true">
            <i
              className="k-grow"
              style={{ width: `${Math.min(100, (MONEY_LEFT_NOW / (budget || 1)) * 100)}%` }}
            />
          </span>
          <span className="k-note">
            {fill(t("v3.spentOf"), {
              a: money(Math.max(0, budget - MONEY_LEFT_NOW), 0),
              b: money(budget, 0),
            })}
          </span>
        </div>
        <div>
          <span className="k-eyebrow">{t("v2.setBudget")}</span>
          {editB ? (
            <div className="pf-edit k-in">
              <input
                className="k-input"
                type="number"
                step={1000}
                value={budget}
                aria-label={t("v2.setBudget")}
                onChange={(e) => setBudget(Number(e.target.value))}
              />
              <button
                type="button"
                className="sk-btn sk-tonal"
                onClick={() => {
                  setEditB(false);
                  if (settings.data) saveBudget.mutate(budget);
                  watch.say(t("v2.budgetSet"));
                }}
              >
                {t("pf.save")}
              </button>
            </div>
          ) : (
            <p className="pf-line">
              <b className="pf-big num">{money(budget, 0)}</b>
              <button type="button" className="k-link" onClick={() => setEditB(true)}>
                {t("v2.change")}
              </button>
            </p>
          )}
          <span className="k-note">{t("pf.budgetP")}</span>
        </div>
      </div>
      <div className="pf-mixh">
        <span className="k-eyebrow">{t("v2.pMix")}</span>
        <button type="button" className="k-link" onClick={() => setEditM(!editM)}>
          {editM ? t("pf.done") : t("pf.editMix")}
        </button>
      </div>
      {editM ? (
        <div className="pf-mixedit k-in">
          {Object.entries(target).map(([s, g]) => (
            <label key={s} className="pf-slider">
              <span>{s}</span>
              <input
                type="range"
                min={0}
                max={40}
                value={g}
                aria-label={`${s} ${t("v2.mixTarget")}`}
                onChange={(e) => setTarget({ ...target, [s]: Number(e.target.value) })}
              />
              <b className="num">{g}%</b>
            </label>
          ))}
          <div className="k-bar">
            <span className={`k-note num ${sum === 100 ? "up" : "dn"}`}>
              {t("v3.mixSum").replace("{n}", String(sum))}
            </span>
            <button
              type="button"
              className="sk-btn sk-tonal"
              disabled={sum !== 100}
              onClick={() => {
                setEditM(false);
                watch.say(t("v2.approvedT"));
              }}
            >
              {t("v2.approveT")}
            </button>
            <button type="button" className="sk-btn" onClick={() => setTarget(TARGET)}>
              {t("v3.mixReset")}
            </button>
          </div>
        </div>
      ) : (
        <div className="pf-mix">
          {gaps.slice(0, 6).map(({ s, g, v }) => (
            <div key={s} className="pf-mixrow">
              <span className="trunc">{s}</span>
              <span className="pf-mixbar" aria-hidden="true">
                <i className="k-grow" style={{ width: `${Math.min(100, v * 2)}%` }} />
                <em style={{ left: `${Math.min(100, g * 2)}%` }} />
              </span>
              <b className={`num ${v - g > 3 ? "dn" : v - g < -3 ? "up" : ""}`}>
                {v.toFixed(0)}% / {g}%
              </b>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function Tax({ rows }: { rows: Rows }) {
  const t = useWords();
  const booked = 84000 + rows.length * 3200;
  const room = Math.max(0, 125000 - booked);
  const losers = rows.filter((r) => r.h.gain < 0);
  return (
    <section className="card pf-card k-up" style={{ "--i": 1 } as React.CSSProperties}>
      <h2>{t("v2.pRoom")}</h2>
      <b className="pf-big num up">{money(room, 0)}</b>
      <span className="k-bar-h gain" aria-hidden="true">
        <i className="k-grow" style={{ width: `${Math.min(100, (booked / 125000) * 100)}%` }} />
      </span>
      <span className="k-note">
        {t("v2.pYear")} {money(booked, 0)}
      </span>
      {losers.length ? (
        <ul className="pf-ul">
          {losers.map((r) => (
            <li key={r.st.id}>
              {fill(t("pf.harvest"), {
                n: r.st.name,
                s: money(Math.abs(r.h.gain) * 0.125, 0),
              })}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

const LOTS = [
  { qty: 40, each: 6120 },
  { qty: 38, each: 7040 },
  { qty: 36, each: 8310 },
];
function Rsu() {
  const t = useWords();
  const price = 9480;
  const qty = LOTS.reduce((a, l) => a + l.qty, 0);
  const cost = LOTS.reduce((a, l) => a + l.qty * l.each, 0);
  return (
    <section className="card pf-card k-up" style={{ "--i": 2 } as React.CSSProperties}>
      <h2>
        {t("v3.tab.rsu")} · {t("v2.rsuWorth").toLowerCase()}
      </h2>
      <b className="pf-big num">{lakh(qty * price)}</b>
      <span className="k-note num">
        {qty} {t("v2.rsuShares")} · {t("v2.rsuProfit")}{" "}
        <b className="up">{lakh(qty * price - cost)}</b>
      </span>
      <span className="k-note">{t("pf.rsuNext")}</span>
    </section>
  );
}

const EVENTS = [
  { d: "3 Dec", id: "echo-bank", kind: "dividend", per: 14 },
  { d: "12 Dec", id: "harbor-ports", kind: "result", per: 0 },
  { d: "9 Jan", id: "delta-power", kind: "bonus", per: 0 },
];
function Coming({ rows }: { rows: Rows }) {
  const t = useWords();
  return (
    <section className="card pf-card k-up" style={{ "--i": 3 } as React.CSSProperties}>
      <h2>{t("v2.mEvents")}</h2>
      <ul className="pf-ev">
        {EVENTS.map((e) => {
          const r = rows.find((x) => x.st.id === e.id);
          if (!r) return null;
          return (
            <li key={e.d}>
              <b className="num">{e.d}</b>
              <span className="trunc">{r.st.name}</span>
              <span className="k-pill">{t(`v3.ev.${e.kind}`)}</span>
              {e.per ? <span className="num up">{money(e.per * r.h.qty, 0)}</span> : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function Holdings({ rows }: { rows: Rows }) {
  const t = useWords();
  const total = rows.reduce((a, r) => a + r.h.value, 0) || 1;
  const sorted = [...rows].sort((a, b) => b.h.value - a.h.value);
  return (
    <div className="k-scroll card pf-tablewrap">
      <table className="k-table pf-table">
        <thead>
          <tr>
            <th>{t("v2.hHolding")}</th>
            <th className="r">{t("v2.hValue")}</th>
            <th className="r">{t("v2.hGain")}</th>
            <th>{t("v2.hShare")}</th>
            <th className="r">{t("pf.chance")}</th>
            <th className="r">{t("v2.lotQ")}</th>
            <th>{t("v2.hHeld")}</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r, i) => (
            <tr key={r.st.id} className="k-up" style={{ "--i": i } as React.CSSProperties}>
              <td>
                <span className="pf-name">
                  <VChip v={r.st.verdict} />
                  <b>{r.st.name}</b>
                  <span className="k-note">{r.h.account}</span>
                </span>
              </td>
              <td className="r num">{money(r.h.value, 0)}</td>
              <td className={`r num ${r.h.gain >= 0 ? "up" : "dn"}`}>
                {money(r.h.gain, 0)} <span className="k-note">{pct(r.h.gainPct)}</span>
              </td>
              <td className="pf-share num">
                <span className="k-bar-h">
                  <i className="k-grow" style={{ width: `${(r.h.value / total) * 220}%` }} />
                </span>
                {((r.h.value / total) * 100).toFixed(1)}%
              </td>
              <td className="r num">{callCard(r.st).chance}%</td>
              <td className="r num">{r.h.qty}</td>
              <td>
                <span className={`k-pill ${r.h.longTerm ? "better" : ""}`}>
                  {r.h.longTerm ? t("v2.rsuLong") : `${t("v3.shortTerm")} · ${r.h.ltFrom}`}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PortfolioScreen() {
  const t = useWords();
  const [scope, setScope] = useState<Scope>("all");
  const rows = HOLDINGS.filter(
    (r) => scope === "all" || (scope === "kite") === (r.h.account === "Kite"),
  );
  const value = rows.reduce((a, r) => a + r.h.value, 0);
  const cost = rows.reduce((a, r) => a + r.h.cost, 0);
  const shown = useCountUp(value);
  return (
    <section className="pf">
      <header className="pf-head">
        <div>
          <p className="k-eyebrow">{t("v2.portfolio")}</p>
          <h1 className="num">{lakh(Math.round(shown))}</h1>
          <p className="k-note">
            {t("v2.pGain")}:{" "}
            <b className={`num ${value >= cost ? "up" : "dn"}`}>
              {money(value - cost, 0)} ({pct((value / (cost || 1) - 1) * 100)})
            </b>{" "}
            · {rows.length} {t("pf.holdings")}
          </p>
        </div>
        <Seg
          label={t("v2.srcT")}
          value={scope}
          onChange={setScope}
          options={[
            { id: "all", label: t("v2.srcAll") },
            { id: "kite", label: t("v2.srcKite") },
            { id: "sc", label: t("v2.srcSc") },
          ]}
        />
      </header>
      <div className="pf-top">
        <Month rows={HOLDINGS} />
        <Tax rows={rows} />
        <Rsu />
        <Coming rows={rows} />
      </div>
      <Holdings rows={rows} />
      <Toast />
      <p className="k-sample">{t("v2.proto")}</p>
    </section>
  );
}
const pane: Pane = {
  id: "portfolio",
  path: "/portfolio",
  titleKey: "shell.nav.portfolio",
  Component: PortfolioScreen,
};
export default pane;
