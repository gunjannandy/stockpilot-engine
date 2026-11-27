import { useMemo, useState } from "react";
import type { Pane } from "../../areas";
import { StockChart } from "../../charts/StockChart";
import { ListAndPane } from "../../shell/ListAndPane";
import { useWords } from "../../words";
import "./stock.css";
import { history, openLinks, type SampleStock, STOCKS } from "./sample";

function OpenIn({ st }: { st: SampleStock }) {
  const t = useWords();
  const l = openLinks(st);
  return (
    <details className="openin">
      <summary>{t("stock.openIn")} ▾</summary>
      <div className="openin-menu">
        <a href={l.kite} target="_blank" rel="noreferrer noopener">
          {t("stock.kite")}
        </a>
        <a href={l.screener} target="_blank" rel="noreferrer noopener">
          {t("stock.screener")}
        </a>
      </div>
    </details>
  );
}

function Detail({ st }: { st: SampleStock }) {
  const t = useWords();
  const bars = useMemo(() => history(st), [st]);
  const last = bars[bars.length - 1]?.close ?? 0;
  const day = (last / (bars[bars.length - 2]?.close ?? last) - 1) * 100;
  const age =
    st.ageSeconds < 90
      ? t("stock.live").replace("{n}", String(st.ageSeconds))
      : t("stock.liveMin").replace("{n}", String(Math.round(st.ageSeconds / 60)));
  return (
    <article className="detail stock-detail">
      <header className="detail-head">
        <div>
          <h1>{st.name}</h1>
          <p className="note">
            {st.symbol} · {st.sector} · {st.exchange}
          </p>
        </div>
        <div className="stock-px">
          <p className="hero num">₹{last.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</p>
          <p className="note">
            <span className={day >= 0 ? "up" : "dn"}>
              {day >= 0 ? "+" : ""}
              {day.toFixed(1)}% {t("stock.today")}
            </span>{" "}
            · {age}
          </p>
        </div>
      </header>
      <section className="card stock-chart-card">
        <div className="stock-chart-head">
          <div>
            <h2>{t("stock.chart")}</h2>
            <p className="note">{t("stock.chartNote")}</p>
          </div>
          <OpenIn st={st} />
        </div>
        <StockChart bars={bars} buys={st.buys} />
      </section>
      <p className="note">{t("stock.sample")}</p>
      <p className="note stock-notice">
        {t("stock.notice")}{" "}
        <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer noopener">
          {t("stock.noticeLink")}
        </a>
      </p>
    </article>
  );
}

export function StockPane() {
  const t = useWords();
  const [q] = useState("");
  const items = STOCKS.filter((s) => s.name.toLowerCase().includes(q));
  return (
    <ListAndPane
      items={items}
      label={t("stock.title")}
      renderRow={(s) => (
        <span className="lp-name">
          <b>{s.name}</b>
          <span className="note">
            {s.symbol} · {s.exchange}
          </span>
        </span>
      )}
      renderPane={(s) => <Detail st={s} />}
    />
  );
}

const pane: Pane = { id: "stock", path: "/stock", titleKey: "stock.title", Component: StockPane };
export default pane;
