// Watchlist: the stocks we chose to watch, read from /api/watchlist. Star on and off, and Hide for 30 days
// (with Undo), write to the API through the shared watch store (/api/watchlist, /api/not-now).
import { screenRoutes, type WatchlistResponse } from "@stockpilot/contract";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import type { Pane as PaneDef } from "../../areas";
import { pct } from "../../format";
import { Pane } from "../../panekit";
import { useWords } from "../../words";
import { ListPage } from "../_kit/ListPage";
import type { StockView, Verdict } from "../_kit/pending";
import { Toast } from "../_kit/Toast";
import { useWatch, watch } from "../_kit/watch";
import { fundRows, stockRows } from "./rows";

function Hidden({ data }: { data: WatchlistResponse }) {
  const t = useWords();
  const w = useWatch();
  const names = new Map(data.items.map((i) => [i.id, i.name ?? i.id]));
  const ids = [...w.snooze];
  if (!ids.length) return null;
  return (
    <section className="k-tile card wl-hidden">
      <h2 className="k-eyebrow">{t("v2.setHidden")}</h2>
      {ids.map((id) => (
        <div key={id} className="wl-hrow">
          <b>{names.get(id) ?? id}</b>
          <button type="button" className="k-link" onClick={() => watch.set("snooze", id, false)}>
            {t("v2.backSnooze")}
          </button>
        </div>
      ))}
    </section>
  );
}

function Funds({ data }: { data: WatchlistResponse }) {
  const t = useWords();
  const w = useWatch();
  const funds = fundRows(data).filter((f) => w.star.has(f.id));
  if (!funds.length) return null;
  return (
    <section className="k-tile card wl-funds">
      <h2 className="k-eyebrow">{t("watchlist.funds")}</h2>
      {funds.map((f) => (
        <div key={f.id} className="wl-hrow">
          <b>{f.name}</b>
          <button
            type="button"
            className="k-link"
            onClick={() => watch.toggleStar(f.id, t("v2.added"), t("v2.removed"), f.name, "fund")}
          >
            {t("v2.remWl")}
          </button>
        </div>
      ))}
    </section>
  );
}

function Body({ data }: { data: WatchlistResponse }) {
  const t = useWords();
  const qc = useQueryClient();
  const w = useWatch();
  // `t` is a new function each render; the effect must run once per answer, not once per render.
  const say = useRef(t);
  say.current = t;
  // Load the saved stars and hidden stocks into the shared store; a later write re-reads the answer.
  useEffect(() => {
    watch.hydrate(
      data.items.map((i) => i.id),
      data.not_now.map((n) => n.symbol),
      () => void qc.invalidateQueries({ queryKey: ["pane", screenRoutes.watchlist.path] }),
      say.current("watchlist.saveFailed"),
    );
  }, [data, qc]);
  const rows: StockView[] = stockRows(data).filter((s) => w.star.has(s.id));
  const best = [...rows].sort((a, b) => b.strength - a.strength)[0];
  const near = rows.filter((s) => s.verdict === "buy").length;
  const sub = t("watchlist.line")
    .replace("{n}", String(near))
    .replace("{b}", best ? `${best.name} ${pct(best.strength, 0).replace("+", "")}` : "–");
  return (
    <>
      <ListPage
        live
        eyebrow={t("v2.watchlist")}
        title={`${rows.length} ${t("v3.watching")}`}
        sub={rows.length ? sub : ""}
        rows={rows}
        chips={[{ id: "all", label: t("v2.all"), test: () => true }]}
        groupOf={(s) => ({
          id: s.verdict,
          label: t(`stock.group.${s.verdict}`),
          cls: `r-${s.verdict}`,
        })}
        groupOrder={["sell", "weak", "buy", "keep", "watch"] satisfies Verdict[]}
        empty={t("v3.watchEmpty")}
        tableCols={["sector"]}
      />
      <Funds data={data} />
      <Hidden data={data} />
      <Toast />
    </>
  );
}

function Watchlist() {
  const t = useWords();
  return (
    <Pane<WatchlistResponse>
      id="watchlist"
      title={t("v2.watchlist")}
      route={screenRoutes.watchlist}
      // The list has no time of its own; the newest thing on it is when it last changed.
      updatedAt={(d) =>
        d.items
          .map((i) => i.added_at)
          .sort()
          .at(-1) ?? null
      }
      windowHours={24 * 365}
    >
      {(d) => <Body data={d} />}
    </Pane>
  );
}

const pane: PaneDef = {
  id: "watchlist",
  path: "/watchlist",
  titleKey: "shell.nav.watchlist",
  Component: Watchlist,
};
export default pane;
