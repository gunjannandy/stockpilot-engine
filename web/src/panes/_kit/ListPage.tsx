// One list page shape for Worth following, Watchlist and Today's siblings: heading, chips, filter, List/Table, list + detail pane.
import { type ReactNode, useEffect, useState } from "react";
import { useWords } from "../../words";
import { Detail } from "../stock";
import { barsOf, callCard, growthOf, peOf, quote, type StockView } from "./pending";
import { Toast } from "./Toast";
import { Seg, StockRow, StockTable } from "./ui";
import { useWatch, watch } from "./watch";

export type Group = { id: string; label: string; sentence?: string; cls: string };
export type ChipDef = { id: string; label: string; test: (s: StockView) => boolean };

export function ListPage({
  eyebrow,
  title,
  sub,
  rows,
  chips,
  groupOf,
  groupOrder,
  reasonsOf,
  top,
  tableCols,
  empty,
  updated,
  rowExtra,
  live,
}: {
  eyebrow: string;
  title: string;
  sub: string;
  rows: StockView[];
  chips: ChipDef[];
  groupOf: (s: StockView) => Group;
  groupOrder: string[];
  reasonsOf?: (s: StockView) => string[];
  top?: ReactNode;
  tableCols?: ("sector" | "pe" | "growth")[];
  empty: string;
  updated?: string;
  rowExtra?: (s: StockView) => ReactNode;
  /** True when the rows come from the API: the prototype note is not shown. */
  live?: boolean;
}) {
  const t = useWords();
  const w = useWatch();
  const [chip, setChip] = useState("all");
  const [q, _setQ] = useState("");
  const [view, setView] = useState<"list" | "table">("list");
  const [sel, setSel] = useState<string>("");
  const [full, setFull] = useState(false);
  const [sf, setSf] = useState<Record<string, string>>({});
  const def = chips.find((c) => c.id === chip);
  const vis = rows.filter(
    (s) =>
      !w.snooze.has(s.id) &&
      !w.never.has(s.id) &&
      (s.name + s.symbol).toLowerCase().includes(q.toLowerCase()) &&
      (!def || chip === "all" || def.test(s)),
  );
  const cur = vis.find((s) => s.id === sel) ?? vis[0];
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA")) return;
      if (e.key === "Escape") setFull(false);
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      const i = vis.findIndex((x) => x.id === cur?.id);
      const n = vis[Math.max(0, Math.min(vis.length - 1, i + (e.key === "ArrowDown" ? 1 : -1)))];
      if (n) {
        e.preventDefault();
        setSel(n.id);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });
  const ordered = [...vis].sort(
    (a, b) =>
      groupOrder.indexOf(groupOf(a).id) - groupOrder.indexOf(groupOf(b).id) ||
      b.strength - a.strength,
  );
  const pick = (id: string, open = true) => {
    setSel(id);
    if (open) setFull(true);
  };
  let last = "";
  return (
    <section className="lp-page">
      <header className="k-head">
        <p className="k-eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p>{sub}</p>
        {updated ? <p className="k-note">{updated}</p> : null}
      </header>
      {top}
      <div className="k-bar">
        <div className="k-chips">
          {chips.map((c) => (
            <button
              key={c.id}
              type="button"
              className="k-chipbtn"
              aria-pressed={chip === c.id}
              onClick={() => setChip(c.id)}
            >
              {c.label}
              <span className="num">
                {c.id === "all" ? rows.length : rows.filter(c.test).length}
              </span>
            </button>
          ))}
        </div>
        <Seg
          label={t("v3.listView")}
          value={view}
          onChange={setView}
          options={[
            { id: "list", label: t("v3.listView") },
            { id: "table", label: t("v3.tableView") },
          ]}
        />
      </div>
      {vis.length === 0 ? (
        <p className="k-note k-tile card">{empty}</p>
      ) : view === "table" ? (
        <>
          <Screener sf={sf} setSf={setSf} total={vis.length} />
          <StockTable
            rows={vis.filter((s) => matchScreen(s, sf))}
            cols={tableCols}
            onPick={(id) => {
              setView("list");
              pick(id);
            }}
          />
        </>
      ) : (
        <div className="sk-lp" data-full={full ? "pane" : "list"}>
          <nav className="sk-list" aria-label={title}>
            {ordered.map((s) => {
              const g = groupOf(s);
              const head = g.id !== last;
              last = g.id;
              return (
                <div key={s.id}>
                  {head && (
                    <>
                      <div className={`lgh ${g.cls}`}>
                        <b>{g.label}</b>
                        <span className="n num">
                          {ordered.filter((x) => groupOf(x).id === g.id).length}
                        </span>
                      </div>
                      {g.sentence ? <p className="td-gp">{g.sentence}</p> : null}
                    </>
                  )}
                  <StockRow
                    st={s}
                    active={cur?.id === s.id}
                    onClick={() => pick(s.id)}
                    mark={!!callCard(s).changed && !w.seen.has(s.id)}
                    reasons={
                      reasonsOf ? (
                        <span className="k-why">
                          {reasonsOf(s).map((r) => (
                            <span key={r}>{r}</span>
                          ))}
                        </span>
                      ) : undefined
                    }
                    star={
                      <button
                        type="button"
                        className="k-star"
                        aria-pressed={w.star.has(s.id)}
                        aria-label={t("v2.watchStar")}
                        onClick={() =>
                          watch.toggleStar(s.id, t("v2.added"), t("v2.removed"), s.name)
                        }
                      >
                        {w.star.has(s.id) ? "★" : "☆"}
                      </button>
                    }
                  />
                  {rowExtra?.(s)}
                </div>
              );
            })}
          </nav>
          <aside className="sk-pane">
            <button type="button" className="sk-back" onClick={() => setFull(false)}>
              ← {t("stock.back")}
            </button>
            {cur ? (
              <Detail st={cur} bars={barsOf(cur)} onPick={pick} />
            ) : (
              <p className="k-note">{t("v3.pickRow")}</p>
            )}
          </aside>
        </div>
      )}
      <Toast />
      {live ? null : <p className="k-sample">{t("v2.proto")}</p>}
    </section>
  );
}
export { quote };

const SCREEN: Record<
  string,
  { label: string; opts: { id: string; label: string; test: (s: StockView) => boolean }[] }
> = {
  verdict: {
    label: "v3.fVerdict",
    opts: (["sell", "weak", "buy", "keep", "watch"] as const).map((v) => ({
      id: v,
      label: `stock.verdict.${v}`,
      test: (s: StockView) => s.verdict === v,
    })),
  },
  pe: {
    label: "v2.uPe",
    opts: [
      { id: "lt", label: "v2.uPeLt15", test: (s) => peOf(s) < 15 },
      { id: "mid", label: "v2.uPeMid", test: (s) => peOf(s) >= 15 && peOf(s) <= 30 },
      { id: "gt", label: "v2.uPeGt30", test: (s) => peOf(s) > 30 },
    ],
  },
  growth: {
    label: "v2.uGrowth",
    opts: [
      { id: "up", label: "v2.uGrUp", test: (s) => growthOf(s) > 15 },
      { id: "slow", label: "v2.uGrSlow", test: (s) => growthOf(s) >= 0 && growthOf(s) <= 15 },
      { id: "down", label: "v2.uGrDown", test: (s) => growthOf(s) < 0 },
    ],
  },
  chance: {
    label: "v2.uChance",
    opts: [
      { id: "60", label: "v2.uChP60", test: (s) => s.strength >= 60 },
      { id: "50", label: "v2.uChP50", test: (s) => s.strength >= 50 && s.strength < 60 },
      { id: "lo", label: "v2.uChLow", test: (s) => s.strength < 50 },
    ],
  },
};
const matchScreen = (s: StockView, sf: Record<string, string>) =>
  Object.entries(sf).every(([k, v]) => !v || SCREEN[k]?.opts.find((o) => o.id === v)?.test(s));

function Screener({
  sf,
  setSf,
  total,
}: {
  sf: Record<string, string>;
  setSf: (v: Record<string, string>) => void;
  total: number;
}) {
  const t = useWords();
  const any = Object.values(sf).some(Boolean);
  return (
    <div className="k-screen card">
      {Object.entries(SCREEN).map(([k, g]) => (
        <div key={k} className="k-sgroup">
          <span className="k-eyebrow">{t(g.label)}</span>
          <div className="k-chips">
            {g.opts.map((o) => (
              <button
                key={o.id}
                type="button"
                className="k-chipbtn"
                aria-pressed={sf[k] === o.id}
                onClick={() => setSf({ ...sf, [k]: sf[k] === o.id ? "" : o.id })}
              >
                {t(o.label)}
              </button>
            ))}
          </div>
        </div>
      ))}
      {any && (
        <button type="button" className="k-link" onClick={() => setSf({})}>
          {t("v2.uClear")}
        </button>
      )}
      <span className="k-note">
        {total} {t("v2.uStocks")}
      </span>
    </div>
  );
}
