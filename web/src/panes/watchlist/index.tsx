// Watchlist: the stocks we chose to watch. Star on, star off, add inline, Hide for 30 days, Undo.
import type { Pane } from "../../areas";
import { useWords } from "../../words";
import { pct, quote, UNIVERSE, universeById } from "../_kit/data";
import { ListPage } from "../_kit/ListPage";
import { Toast } from "../_kit/Toast";
import { useWatch, watch } from "../_kit/watch";

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

const wlLine = (rows: typeof UNIVERSE, tpl: string) => {
  const day = (s: (typeof UNIVERSE)[number]) => quote(s).day;
  const best = [...rows].sort((a, b) => day(b) - day(a))[0];
  const near = rows.filter((s) => s.verdict === "buy").length;
  return tpl
    .replace("{n}", String(near))
    .replace("{b}", best ? `${best.name} ${pct(day(best))}` : "–");
};

function Watchlist() {
  const t = useWords();
  const w = useWatch();
  const rows = UNIVERSE.filter((s) => w.star.has(s.id));
  return (
    <>
      <ListPage
        eyebrow={t("v2.watchlist")}
        title={`${rows.length} ${t("v3.watching")}`}
        sub={wlLine(rows, t("v3.wlLine"))}
        rows={rows}
        chips={[{ id: "all", label: t("v2.all"), test: () => true }]}
        groupOf={(s) => ({
          id: s.verdict,
          label: t(`stock.group.${s.verdict}`),
          cls: `r-${s.verdict}`,
        })}
        groupOrder={["sell", "weak", "buy", "keep", "watch"]}
        empty={t("v3.watchEmpty")}
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
