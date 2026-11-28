// Watchlist: the stocks we chose to watch. Star on, star off, add inline, Hide for 30 days, Undo.
import type { Pane } from "../../areas";
import { useWords } from "../../words";
import { pct, quote, UNIVERSE, universeById } from "../_kit/data";
import { Find } from "../_kit/Find";
import { ListPage } from "../_kit/ListPage";
import { Toast } from "../_kit/Toast";
import { useWatch, watch } from "../_kit/watch";

function Add() {
  const t = useWords();
  const w = useWatch();
  return (
    <Find
      placeholder={t("v2.watchAdd")}
      actionLabel={t("v2.addWl")}
      skip={(id) => w.star.has(id)}
      onPick={(id) => watch.toggleStar(id, t("v2.added"), t("v2.removed"))}
    />
  );
}

/** Four numbers to read before the list: what is close to a buy, who rose, who fell, and what needs a look. */
function Glance({ rows }: { rows: typeof UNIVERSE }) {
  const t = useWords();
  const day = (s: (typeof UNIVERSE)[number]) => quote(s).day;
  const best = [...rows].sort((a, b) => day(b) - day(a))[0];
  const worst = [...rows].sort((a, b) => day(a) - day(b))[0];
  const near = rows.filter((s) => s.verdict === "buy").length;
  const flagged = rows.filter((s) => s.verdict === "sell" || s.verdict === "weak").length;
  const cards = [
    { k: "near", label: t("v3.wlNear"), v: String(near), tone: "up", note: t("v3.wlNearP") },
    {
      k: "best",
      label: t("v3.wlBest"),
      v: best ? pct(day(best)) : "–",
      tone: "up",
      note: best?.name ?? "",
    },
    {
      k: "worst",
      label: t("v3.wlWorst"),
      v: worst ? pct(day(worst)) : "–",
      tone: "dn",
      note: worst?.name ?? "",
    },
    { k: "flag", label: t("v3.wlFlag"), v: String(flagged), tone: "", note: t("v3.wlFlagP") },
  ];
  return (
    <div className="wl-glance">
      {cards.map((c, i) => (
        <div key={c.k} className="wl-g" style={{ animationDelay: `${i * 60}ms` }}>
          <span className="k-eyebrow">{c.label}</span>
          <b className={`num ${c.tone}`}>{c.v}</b>
          <span className="k-note">{c.note}</span>
        </div>
      ))}
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
        top={
          <>
            <Glance rows={rows} />
            <Add />
          </>
        }
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
