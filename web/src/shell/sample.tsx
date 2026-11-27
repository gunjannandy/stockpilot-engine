// Sample screens for the prototype: made-up rows so the frame can be judged. Real areas replace
// these by dropping their own pane folder in; nothing here is real market data.
import type { FunctionComponent } from "react";
import type { Pane } from "../areas";
import { useWords } from "../words";
import { ListAndPane, type Row } from "./ListAndPane";

type Verdict = "sell" | "weak" | "buy" | "keep";
type Stock = Row & {
  name: string;
  sector: string;
  verdict: Verdict;
  price: string;
  day: number;
  held: string;
  cost: string;
  range: string;
  volume: string;
  seed: number;
  view: string;
  risks: string[];
};
const ORDER: Verdict[] = ["sell", "weak", "buy", "keep"];
const mk = (
  name: string,
  sector: string,
  verdict: Verdict,
  price: number,
  day: number,
  seed: number,
  view: string,
): Stock => ({
  id: name.toLowerCase().replace(/\W+/g, "-"),
  group: verdict,
  name,
  sector,
  verdict,
  price: price.toLocaleString("en-IN", { minimumFractionDigits: 2 }),
  day,
  held: `${10 + seed * 7} shares`,
  cost: (price * (0.8 + (seed % 5) / 10)).toLocaleString("en-IN", { maximumFractionDigits: 2 }),
  range: `${Math.round(price * 0.7)} – ${Math.round(price * 1.25)}`,
  volume: `${(seed * 0.37 + 0.4).toFixed(1)} lakh`,
  seed,
  view,
  risks: ["Sales growth is slowing.", "Debt rose over the last two quarters."].slice(
    0,
    1 + (seed % 2),
  ),
});
const STOCKS: Stock[] = [
  mk(
    "Alpha Steel",
    "Metals",
    "sell",
    412.5,
    -2.4,
    3,
    "Sell today. The price has broken its recent floor and the news is poor.",
  ),
  mk(
    "Bravo Motors",
    "Auto",
    "sell",
    1288.1,
    -1.1,
    5,
    "Sell on the next bounce. Margins are shrinking.",
  ),
  mk(
    "Cedar Pharma",
    "Health",
    "weak",
    905.0,
    -0.4,
    2,
    "Weak. Do not add. Wait for the next result.",
  ),
  mk("Delta Power", "Energy", "weak", 233.8, 0.3, 4, "Weak. Hold what we have, no new money."),
  mk(
    "Echo Bank",
    "Banks",
    "buy",
    1641.2,
    1.8,
    6,
    "Buy a little. Earnings beat and the price is near support.",
  ),
  mk("Foxtrot Foods", "Consumer", "buy", 2790.0, 0.9, 1, "Buy on dips. Steady growth, fair price."),
  mk("Gamma Tech", "IT", "buy", 1522.4, 2.2, 7, "Buy. Orders are up and the chart is clean."),
  mk("Harbor Ports", "Transport", "keep", 1104.9, 0.1, 8, "Keep. Nothing to do today."),
  mk(
    "Indigo Cement",
    "Materials",
    "keep",
    3150.6,
    -0.2,
    9,
    "Keep. Fairly priced, no change in view.",
  ),
  mk("Juno Finance", "Finance", "keep", 718.3, 0.6, 10, "Keep. Wait for the next result."),
  mk("Kilo Retail", "Retail", "keep", 456.7, -0.7, 11, "Keep. Small position, low risk."),
  mk("Lima Telecom", "Telecom", "keep", 1893.0, 0.4, 12, "Keep. Steady, nothing new."),
  mk("Mike Chemicals", "Chemicals", "keep", 2201.5, -0.3, 13, "Keep. Demand is flat."),
  mk("Nova Realty", "Property", "keep", 987.2, 1.0, 14, "Keep. No action."),
];

function spark(seed: number): string {
  let y = 50;
  const pts: string[] = [];
  for (let i = 0; i < 40; i++) {
    y +=
      Math.sin(i * 0.5 + seed) * 6 +
      Math.cos(i * 0.21 + seed * 2) * 4 -
      0.4 * (seed % 3 === 0 ? -1 : 1);
    y = Math.max(8, Math.min(92, y));
    pts.push(`${(i / 39) * 300},${100 - y}`);
  }
  return pts.join(" ");
}

function StockList() {
  const t = useWords();
  const items = [...STOCKS]
    .sort((a, b) => ORDER.indexOf(a.verdict) - ORDER.indexOf(b.verdict))
    .map((s) => ({ ...s, groupLabel: t(`shell.verdict.${s.verdict}`) }));
  return (
    <ListAndPane
      items={items}
      label={t("shell.list.label")}
      renderRow={(s) => (
        <>
          <span className={`dot v-${s.verdict}`} aria-hidden="true" />
          <span className="lp-name">
            <b>{s.name}</b>
            <span className="note">{s.sector}</span>
          </span>
          <span className="num lp-price">
            {s.price}
            <span className={s.day >= 0 ? "up" : "dn"}>
              {s.day >= 0 ? "+" : ""}
              {s.day.toFixed(1)}%
            </span>
          </span>
        </>
      )}
      renderPane={(s) => (
        <article className="detail">
          <header className="detail-head">
            <div>
              <h1>{s.name}</h1>
              <p className="note">{s.sector}</p>
            </div>
            <span className={`badge v-${s.verdict}`}>{t(`shell.verdict.${s.verdict}`)}</span>
          </header>
          <p className="hero num">
            {s.price}
            <span className={`hero-day ${s.day >= 0 ? "up" : "dn"}`}>
              {s.day >= 0 ? "+" : ""}
              {s.day.toFixed(1)}%
            </span>
          </p>
          <figure className="chart">
            <svg
              viewBox="0 0 300 100"
              preserveAspectRatio="none"
              role="img"
              aria-label={t("shell.chart.note")}
            >
              <polyline points={spark(s.seed)} />
            </svg>
            <figcaption className="note">{t("shell.chart.note")}</figcaption>
          </figure>
          <div className="stats">
            {(
              [
                ["stat.range", s.range],
                ["stat.volume", s.volume],
                ["stat.held", s.held],
                ["stat.cost", s.cost],
              ] as const
            ).map(([k, v]) => (
              <div key={k} className="stat">
                <span className="note">{t(`shell.${k}`)}</span>
                <b className="num">{v}</b>
              </div>
            ))}
          </div>
          <h2>{t("shell.view")}</h2>
          <p>{s.view}</p>
          <h2>{t("shell.risks")}</h2>
          <ul>
            {s.risks.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
          <p className="note">{t("shell.sample.note")}</p>
        </article>
      )}
    />
  );
}

function Stub({ titleKey }: { titleKey: string }) {
  const t = useWords();
  return (
    <section className="stub card">
      <h1>{t(titleKey)}</h1>
      <h2>{t("shell.stub.title")}</h2>
      <p>{t("shell.stub.body")}</p>
    </section>
  );
}
const stub =
  (titleKey: string): FunctionComponent =>
  () => <Stub titleKey={titleKey} />;

const screen = (id: string, Component: FunctionComponent): Pane => ({
  id,
  path: `/${id}`,
  titleKey: `shell.nav.${id}`,
  Component,
});

/** The prototype's screens, in rail order. Replaced as each area's own pane folder lands. */
export const samplePanes: Pane[] = [
  screen("today", StockList),
  screen("worth", StockList),
  screen("portfolio", StockList),
  screen("watchlist", StockList),
  screen("funds", stub("shell.nav.funds")),
  screen("market", stub("shell.nav.market")),
  screen("record", stub("shell.nav.record")),
  screen("feedback", stub("shell.nav.feedback")),
  screen("admin", stub("shell.nav.admin")),
];
