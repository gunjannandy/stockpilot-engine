// Today: the day's call line, calls on held and watched stocks, money left this month, how the market looks.
// Reads GET /api/today through the contract (see web/src/panes/README.md). Sections without data are
// bannered sections (Admin, Screens), not hand-made states.
import { screenRoutes, type TodayResponse } from "@stockpilot/contract";
import type { Pane as PaneDef } from "../../areas";
import { money, pct } from "../../format";
import { Bannered, NumberSlot, Pane } from "../../panekit";
import { fill } from "../../panekit/freshness";
import { getLang } from "../../theme/theme";
import { useWords } from "../../words";
import "./today.css";

const GROUPS = [
  { id: "sell", key: "today.groupSell", cls: "r-sell" },
  { id: "weak", key: "today.groupWeak", cls: "r-weak" },
  { id: "fine_keep", key: "today.groupKeep", cls: "r-keep" },
  { id: "close_to_buy", key: "today.groupBuy", cls: "r-buy" },
  { id: "unusual", key: "today.groupUnusual", cls: "r-watch" },
] as const;

const stockHref = (symbol: string) => `/stock?s=${encodeURIComponent(symbol)}`;

function MoneyLeft({ left }: { left: number | null }) {
  const t = useWords();
  return (
    <section className="td-money" data-testid="today-money">
      <h2 className="k-eyebrow">{t("today.moneyLeft")}</h2>
      {left === null ? (
        <p className="k-note">{t("today.moneyLeftNone")}</p>
      ) : (
        <NumberSlot
          value={money(left)}
          sentence={t("today.moneyLeftSentence")}
          how={t("today.moneyLeftHow")}
        />
      )}
    </section>
  );
}

function Market({ m, lang }: { m: NonNullable<TodayResponse["market"]>; lang: "en" | "bn" }) {
  const t = useWords();
  return (
    <section className="td-health" data-testid="today-market">
      <h2 className="k-eyebrow">{t("today.market")}</h2>
      {m.sentences.map((s) => (
        <p key={s.key}>{s[lang]}</p>
      ))}
      {m.breadth_pct !== null && (
        <NumberSlot
          value={`${m.breadth_pct.toFixed(0)}%`}
          sentence={fill(t("today.breadthSentence"), { n: String(m.breadth_n) })}
          how={t("today.breadthHow")}
        />
      )}
      {m.nifty_trend !== null && m.nifty_trend_pct !== null && (
        <NumberSlot
          value={pct(m.nifty_trend_pct)}
          sentence={t(m.nifty_trend === "up" ? "today.trendUp" : "today.trendDown")}
          how={t("today.trendHow")}
        />
      )}
      {m.median_pe !== null && m.value_band !== null && (
        <NumberSlot
          value={m.median_pe.toFixed(1)}
          sentence={fill(t("today.valueSentence"), { band: t(`today.band.${m.value_band}`) })}
          how={t("today.valueHow")}
        />
      )}
    </section>
  );
}

function Calls({ d }: { d: TodayResponse }) {
  const t = useWords();
  const total = GROUPS.reduce((n, g) => n + d.groups[g.id].length, 0);
  return (
    <section className="td-calls" data-testid="today-calls">
      <p className="k-note">
        {t("today.groupsNote")}
        {d.as_of ? ` ${fill(t("today.callsAsOf"), { day: d.as_of })}` : ""}
      </p>
      {d.stale_held.length > 0 && (
        <p className="k-note" data-testid="today-stale">
          {fill(t("today.staleHeld"), { list: d.stale_held.join(", ") })}
        </p>
      )}
      {total === 0 && <p className="k-note td-empty">{t("today.empty")}</p>}
      {GROUPS.map((g) => {
        const rows = d.groups[g.id];
        if (!rows.length) return null;
        return (
          <div key={g.id} className="td-group">
            <div className={`lgh ${g.cls}`}>
              <b>{t(g.key)}</b>
              <span className="n num">{rows.length}</span>
            </div>
            <ul className="td-syms">
              {rows.map((s) => (
                <li key={s}>
                  <a href={stockHref(s)}>
                    <b>{s}</b> <span>{t("today.open")}</span>
                  </a>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </section>
  );
}

export function TodayScreen() {
  const t = useWords();
  const lang = getLang() === "bn" ? "bn" : "en";
  return (
    <section className="td">
      <Pane<TodayResponse>
        id="today"
        title={t("today.heading")}
        route={screenRoutes.today}
        updatedAt={(d) => (d.as_of ? `${d.as_of}T15:30:00+05:30` : null)}
        windowHours={72}
      >
        {(d) => (
          <>
            <header className="k-head td-head">
              <p className="td-line" data-testid="today-line">
                {d.call_line[lang]}
              </p>
              <button type="button" className="td-print" onClick={() => window.print()}>
                {t("today.print")}
              </button>
            </header>
            <Bannered screen="today" section="calls">
              <Calls d={d} />
            </Bannered>
            <Bannered screen="today" section="money">
              <MoneyLeft left={d.money_left_inr} />
            </Bannered>
            <Bannered screen="today" section="market">
              {d.market ? (
                <Market m={d.market} lang={lang} />
              ) : (
                <section className="td-health">
                  <h2 className="k-eyebrow">{t("today.market")}</h2>
                  <p className="k-note">{t("today.noFigure")}</p>
                </section>
              )}
            </Bannered>
          </>
        )}
      </Pane>
    </section>
  );
}

const pane: PaneDef = {
  id: "today",
  path: "/today",
  titleKey: "today.title",
  Component: TodayScreen,
};
export default pane;
