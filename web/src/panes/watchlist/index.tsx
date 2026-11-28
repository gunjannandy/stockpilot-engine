// Watchlist: the stocks we chose to watch. Star on, star off, add inline, Hide for 30 days, Undo.
import { useState } from "react";
import type { Pane } from "../../areas";
import { useWords } from "../../words";
import { UNIVERSE, universeById } from "../_kit/data";
import { ListPage } from "../_kit/ListPage";
import { Toast } from "../_kit/Toast";
import { useWatch, watch } from "../_kit/watch";

function Add() {
  const t = useWords();
  const w = useWatch();
  const [q, setQ] = useState("");
  const hits =
    q.length > 0
      ? UNIVERSE.filter(
          (s) => !w.star.has(s.id) && (s.name + s.symbol).toLowerCase().includes(q.toLowerCase()),
        ).slice(0, 5)
      : [];
  return (
    <div className="wl-add">
      <input
        className="k-input"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder={t("v2.watchAdd")}
        aria-label={t("v2.searchAdd")}
      />
      {hits.length > 0 && (
        <ul className="wl-hits k-in">
          {hits.map((s) => (
            <li key={s.id}>
              <button
                type="button"
                onClick={() => {
                  watch.toggleStar(s.id, t("v2.added"), t("v2.removed"));
                  setQ("");
                }}
              >
                <b>{s.name}</b>{" "}
                <span className="k-note">
                  {s.symbol} · {s.sector}
                </span>
                <span className="k-link">＋ {t("v2.addWl")}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Hidden() {
  const t = useWords();
  const w = useWatch();
  const ids = [...w.snooze];
  if (!ids.length) return null;
  return (
    <section className="k-tile card wl-hidden">
      <h2 className="k-eyebrow">{t("v2.setHidden")}</h2>
      {ids.map((id) => (
        <div key={id} className="wl-hrow">
          <b>{universeById(id)?.name}</b>
          <button type="button" className="k-link" onClick={() => watch.set("snooze", id, false)}>
            {t("v2.backSnooze")}
          </button>
        </div>
      ))}
    </section>
  );
}

function Watchlist() {
  const t = useWords();
  const w = useWatch();
  const rows = UNIVERSE.filter((s) => w.star.has(s.id));
  return (
    <>
      <ListPage
        eyebrow={t("v2.watchlist")}
        title={`${rows.length} ${t("v3.watching")}`}
        sub={t("v2.wlP")}
        rows={rows}
        chips={[{ id: "all", label: t("v2.all"), test: () => true }]}
        groupOf={(s) => ({
          id: s.verdict,
          label: t(`stock.group.${s.verdict}`),
          cls: `r-${s.verdict}`,
        })}
        groupOrder={["sell", "weak", "buy", "keep", "watch"]}
        empty={t("v3.watchEmpty")}
        top={<Add />}
        tableCols={["sector"]}
      />
      <Hidden />
      <Toast />
    </>
  );
}
const pane: Pane = {
  id: "watchlist",
  path: "/watchlist",
  titleKey: "shell.nav.watchlist",
  Component: Watchlist,
};
export default pane;
