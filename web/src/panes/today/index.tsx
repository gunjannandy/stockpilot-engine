// Today: the answer to "what should we do today?", on v2's layout. Made-up data throughout.
import { useMemo, useState } from "react";
import type { Pane } from "../../areas";
import { useWords } from "../../words";
import { todayLine } from "../_kit/hooks";
import {
  barsOf,
  callCard,
  callLine,
  isHeld,
  NEWS,
  STOCKS,
  stockById,
  todayGroups,
  UNUSUAL,
} from "../_kit/pending";
import { Toast } from "../_kit/Toast";
import { Seg, StockRow, StockTable, VChip } from "../_kit/ui";
import { useWatch, watch } from "../_kit/watch";
import { Detail } from "../stock";
import "./today.css";

const fill = (s: string, v: Record<string, string | number>) =>
  s.replace(/\{(\w+)\}/g, (_, k) => String(v[k] ?? ""));
const GROUPS = [
  { id: "sell", t: "v2.secSell", p: "v2.secSellP", cls: "r-sell" },
  { id: "weak", t: "v2.secWeak", p: "v2.secWeakP", cls: "r-weak" },
  { id: "keep", t: "v2.secKeep", p: "v2.secKeepP", cls: "r-keep" },
  { id: "near", t: "v2.secNear", p: "v2.secNearP", cls: "r-buy" },
  { id: "odd", t: "v2.secOdd", p: "v2.secOddP", cls: "r-watch" },
] as const;

function InNews({ onPick }: { onPick: (id: string) => void }) {
  const t = useWords();
  const seen = new Set<string>();
  const hits = NEWS.flatMap((n) => n.hits).filter(
    (h) => h.rel === "direct" && (seen.has(h.id) ? false : seen.add(h.id)),
  );
  return (
    <section className="td-news">
      <h2 className="k-eyebrow">{t("v3.inNews")}</h2>
      <div className="td-newsgrid">
        {hits.map((h) => {
          const st = stockById(h.id);
          if (!st) return null;
          return (
            <button key={h.id} type="button" className="td-ntile" onClick={() => onPick(st.id)}>
              <b>{st.name}</b>
              <VChip v={st.verdict} />
              <span className={h.dir === "helps" ? "up" : "dn"}>
                {h.dir === "helps" ? `▲ ${t("v3.helps")}` : `▼ ${t("v3.hurts")}`}
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}

function TodayScreen() {
  const t = useWords();
  const w = useWatch();
  const groups = useMemo(() => todayGroups(), []);
  const line = callLine(groups);
  const [vf, setVf] = useState<"all" | (typeof GROUPS)[number]["id"]>("all");
  const [q, _setQ] = useState("");
  const [view, setView] = useState<"list" | "table">("list");
  const [sel, setSel] = useState(line.kind === "act" ? line.first.id : (STOCKS[0]?.id ?? ""));
  const [full, setFull] = useState(false);
  const cur = stockById(sel) ?? STOCKS[0];
  const vis = (s: (typeof STOCKS)[number]) =>
    !w.snooze.has(s.id) &&
    !w.never.has(s.id) &&
    (s.name + s.symbol).toLowerCase().includes(q.toLowerCase());
  const total = GROUPS.reduce((n, g) => n + groups[g.id].filter(vis).length, 0);
  const changed = STOCKS.filter((s) => callCard(s).changed && !w.seen.has(s.id));
  const pick = (id: string, open = true) => {
    setSel(id);
    if (open) setFull(true);
  };
  return (
    <section className="td">
      <header className="k-head td-head">
        <div>
          <p className="k-eyebrow">{todayLine("en")}</p>
          <h1>
            {line.kind === "act"
              ? fill(t("v3.callFirst"), { a: line.first.name })
              : t("v3.callNone")}
          </h1>
          <p>
            {line.kind === "act" ? (
              <>
                {line.after ? fill(t("v3.callAfter"), { b: line.after.name }) : ""}{" "}
                {t("v3.callRest")}
              </>
            ) : (
              t("v3.callNoneP")
            )}
          </p>
        </div>
        <button type="button" className="td-print" onClick={() => window.print()}>
          {t("v3.print")}
        </button>
      </header>
      <InNews onPick={pick} />
      <div className="k-bar td-bar">
        <div className="k-chips">
          <button
            type="button"
            className="k-chipbtn"
            aria-pressed={vf === "all"}
            onClick={() => setVf("all")}
          >
            {t("v2.all")}
            <span className="num">{total}</span>
          </button>
          {GROUPS.map((g) => (
            <button
              key={g.id}
              type="button"
              className="k-chipbtn"
              aria-pressed={vf === g.id}
              onClick={() => setVf(g.id)}
            >
              {t(g.t)}
              <span className="num">{groups[g.id].filter(vis).length}</span>
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
      {view === "table" ? (
        <StockTable
          rows={STOCKS.filter(vis).filter((s) => vf === "all" || groups[vf].includes(s))}
          onPick={(id) => {
            setView("list");
            pick(id);
          }}
        />
      ) : (
        <div className="sk-lp td-lp" data-full={full ? "pane" : "list"}>
          <nav className="sk-list" aria-label={t("v2.today")}>
            {changed.length > 0 && (
              <div className="k-band">
                <i className="k-dot" />
                <b>
                  {changed.length} {t("v3.changedN")}
                </b>
                <button
                  type="button"
                  className="k-link"
                  onClick={() => watch.markSeen(changed.map((s) => s.id))}
                >
                  {t("marks.markAll")}
                </button>
              </div>
            )}
            {GROUPS.filter((g) => vf === "all" || vf === g.id).map((g) => {
              const rows = groups[g.id].filter(vis);
              if (!rows.length) return null;
              return (
                <div key={g.id} className="td-group">
                  <div className={`lgh ${g.cls}`}>
                    <b>{t(g.t)}</b>
                    <span className="n num">{rows.length}</span>
                  </div>
                  <p className="td-gp">{t(g.p)}</p>
                  {rows.map((s) => (
                    <StockRow
                      key={s.id}
                      st={s}
                      active={cur?.id === s.id}
                      onClick={() => pick(s.id)}
                      mark={!!callCard(s).changed && !w.seen.has(s.id)}
                      reasons={
                        <span className="k-why">
                          {isHeld(s) && <span>{t("v2.youHoldT")}</span>}
                          {UNUSUAL[s.id] && <span>{UNUSUAL[s.id]}</span>}
                        </span>
                      }
                      star={
                        <button
                          type="button"
                          className="k-star"
                          aria-pressed={w.star.has(s.id)}
                          aria-label={t("v2.watchStar")}
                          onClick={() => watch.toggleStar(s.id, t("v2.added"), t("v2.removed"))}
                        >
                          {w.star.has(s.id) ? "★" : "☆"}
                        </button>
                      }
                    />
                  ))}
                </div>
              );
            })}
            {total === 0 && <p className="k-note td-empty">{t("v3.nothingHere")}</p>}
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
      <p className="k-sample">{t("v2.proto")}</p>
    </section>
  );
}

const pane: Pane = { id: "today", path: "/today", titleKey: "today.title", Component: TodayScreen };
export default pane;
