// Prototype of Today: one call line, money left, market health, portfolio, grouped stocks, print on one A4 page.
import type { Pane } from "../../areas";
import { useWords } from "../../words";
import { CALL_LINE, type Group, MARKET, MONEY_LEFT, PORTFOLIO, ROWS } from "./sample";
import "./today.css";

const RS = "₹";
const money = (v: number) =>
  `${RS}${v.toLocaleString("en-IN", { maximumFractionDigits: v < 1000 ? 1 : 0 })}`;
const pct = (v: number) => `${v > 0 ? "+" : ""}${v}%`;
const GROUPS: { id: Group; key: string; cls: string }[] = [
  { id: "sell", key: "groupSell", cls: "v-sell" },
  { id: "weak", key: "groupWeak", cls: "v-weak" },
  { id: "keep", key: "groupKeep", cls: "v-keep" },
  { id: "buy", key: "groupBuy", cls: "v-buy" },
  { id: "unusual", key: "groupUnusual", cls: "v-keep" },
];

function TodayScreen() {
  const t = useWords();
  return (
    <section className="td">
      <header className="td-head">
        <h1>{t("today.heading")}</h1>
        <button type="button" className="td-print" onClick={() => window.print()}>
          {t("today.print")}
        </button>
      </header>
      <div className="td-call card" data-testid="call-line">
        <p className="td-call-main">{CALL_LINE.action}</p>
        <p className="td-call-sub">{CALL_LINE.detail}</p>
      </div>
      <div className="td-tiles">
        <div className="td-tile card">
          <h2>{t("today.moneyLeft")}</h2>
          <p className="td-big num">{money(MONEY_LEFT.left)}</p>
          <p className="note">{MONEY_LEFT.note}</p>
        </div>
        <div className="td-tile card">
          <h2>{t("today.portfolio")}</h2>
          <p className="td-big num">{money(PORTFOLIO.worth)}</p>
          <p className="note">
            {t("today.dayChange")}{" "}
            <b className={PORTFOLIO.day >= 0 ? "up" : "dn"}>{pct(PORTFOLIO.day)}</b>
            {" · "}
            {t("today.total")} <b className="up">{pct(PORTFOLIO.total)}</b>
            {" · "}
            {PORTFOLIO.holdings} {t("today.holdings")}
          </p>
        </div>
        <div className="td-tile card td-market">
          <h2>{t("today.market")}</h2>
          <dl>
            <dt>{t("today.breadth")}</dt>
            <dd>
              <b className="num">
                {MARKET.breadth.up} / {MARKET.breadth.of}
              </b>{" "}
              {MARKET.breadth.say}
            </dd>
            <dt>{t("today.trend")}</dt>
            <dd>{MARKET.trend.say}</dd>
            <dt>{t("today.value")}</dt>
            <dd>
              <b>{MARKET.value.band}.</b> {MARKET.value.say}
              <span className="td-band" aria-hidden="true">
                <i style={{ left: `${MARKET.value.at}%` }} />
              </span>
            </dd>
          </dl>
        </div>
      </div>
      {GROUPS.map((g) => {
        const rows = ROWS.filter((r) => r.group === g.id);
        return (
          <section className="td-group card" key={g.id}>
            <h2>
              <span className={`dot ${g.cls}`} /> {t(`today.${g.key}`)}{" "}
              <span className="note">{rows.length}</span>
            </h2>
            {rows.length === 0 ? (
              <p className="note">{t("today.empty")}</p>
            ) : (
              <ul>
                {rows.map((r) => (
                  <li key={r.id}>
                    <span className="td-name">
                      <b>{r.name}</b>
                      <span className="note">{r.sector}</span>
                    </span>
                    <span className="td-why">{r.why}</span>
                    <span className="td-px num">
                      {money(r.price)}
                      <span className={r.day >= 0 ? "up" : "dn"}>{pct(r.day)}</span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        );
      })}
      <p className="note td-sample">{t("today.sample")}</p>
    </section>
  );
}

const pane: Pane = { id: "today", path: "/today", titleKey: "today.title", Component: TodayScreen };
export default pane;
