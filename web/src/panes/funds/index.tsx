import { useMemo, useState } from "react";
import type { Pane } from "../../areas";
import { fill } from "../../panekit";
import { ListAndPane, type Row } from "../../shell/ListAndPane";
import { useWords } from "../../words";
import { FUNDS, type Fund, NIFTY } from "./fixture";
import {
  beatShare,
  buyDots,
  cagr,
  falls,
  RANGES,
  type Range,
  rolling,
  rollStats,
  type Series,
  slice,
  vs,
} from "./funds-core";
import "./funds.css";
import { FundNote, Overlap } from "../fundoverlap/Overlap";

type Item = Fund & Row;
const pct = (n: number | null, d = 1) => (n == null ? "–" : `${n.toFixed(d)}`);
const inr = (n: number) => n.toLocaleString("en-IN", { maximumFractionDigits: 0 });
const money = (n: number) => `₹${inr(n)}`;
const day = (d: string) =>
  new Date(`${d}T00:00:00`).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });

/** The Nifty rebased to the fund's first NAV on the chart, so the two lines start together. */
function rebase(bench: Series, s: Series): number[] {
  const t = Date.parse(s.dates[0] as string);
  let k = 0;
  for (let i = 0; i < bench.dates.length; i++) if (Date.parse(bench.dates[i] as string) <= t) k = i;
  const base = (bench.nav[k] as number) || 1;
  const first = s.nav[0] as number;
  return s.dates.map((d) => {
    const tt = Date.parse(d);
    let j = k;
    while (j + 1 < bench.dates.length && Date.parse(bench.dates[j + 1] as string) <= tt) j++;
    return ((bench.nav[j] as number) / base) * first;
  });
}

function Chart({ fund, range }: { fund: Fund; range: Range }) {
  const t = useWords();
  const s = slice(fund.series, range);
  const bench = rebase(NIFTY, s);
  const W = 600;
  const H = 220;
  const all = [...s.nav, ...bench];
  const lo = Math.min(...all);
  const hi = Math.max(...all);
  const x = (i: number) => (i / (s.nav.length - 1)) * W;
  const y = (v: number) => H - 8 - ((v - lo) / (hi - lo || 1)) * (H - 16);
  const line = (v: number[]) => v.map((n, i) => `${x(i).toFixed(1)},${y(n).toFixed(1)}`).join(" ");
  const dots = buyDots(s, fund.lots);
  return (
    <figure className="fund-chart">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={t("funds.chart.alt")}
        data-testid="nav-chart"
      >
        <polyline className="bench" points={line(bench)} />
        <polyline className="fundline" points={line(s.nav)} />
        {dots.map((d) => (
          <circle
            key={d.acquired_on}
            className="buy"
            data-testid="buy-dot"
            cx={x(d.i)}
            cy={y(s.nav[d.i] as number)}
            r={6}
          />
        ))}
      </svg>
      <figcaption className="fund-legend note">
        <span className="k fundk">{t("funds.chart.fund")}</span>
        <span className="k benchk">{t("funds.chart.nifty")}</span>
        {fund.lots.length ? <span className="k buyk">{t("funds.chart.buy")}</span> : null}
      </figcaption>
    </figure>
  );
}

function Vs({ a, b }: { a: number | null; b: number | null }) {
  const t = useWords();
  const v = vs(a, b);
  return v ? <span className={`vs vs-${v}`}>{t(`funds.${v}`)}</span> : null;
}

function FundPage({ fund }: { fund: Fund }) {
  const t = useWords();
  const [range, setRange] = useState<Range>("5Y");
  const m = useMemo(() => {
    const years = [1, 3, 5] as const;
    const rows = years.map((y) => ({
      y,
      f: cagr(fund.series, y),
      k: cagr(fund.kind, y),
      n: cagr(NIFTY, y),
    }));
    const roll3 = rolling(fund.series, 3);
    return {
      rows,
      roll: rollStats(roll3),
      beat: beatShare(fund.series, NIFTY, 1),
      falls: falls(fund.series, NIFTY),
    };
  }, [fund]);
  const navNow = fund.series.nav[fund.series.nav.length - 1] as number;
  const prev = fund.series.nav[fund.series.nav.length - 2] as number;
  const chg = ((navNow / prev - 1) * 100) as number;
  const headline = [...m.rows].reverse().find((r) => r.f != null);
  const cost1000 = (fund.cost * 10).toFixed(2).replace(/\.?0+$/, "");
  const held = fund.lots.reduce((a, l) => a + l.quantity, 0);
  return (
    <article className="detail fund" data-testid="fund-page">
      <header className="detail-head">
        <div>
          <h1>{fund.name}</h1>
          <p className="note">
            {fund.amc} · {fund.category}
          </p>
        </div>
        <span className={`badge ${held ? "v-buy" : "v-keep"}`}>
          {held ? t("funds.held") : t("funds.not.held")}
        </span>
      </header>
      <p className="hero num">
        {navNow.toFixed(2)}
        <span className={`hero-day ${chg >= 0 ? "up" : "dn"}`}>
          {chg >= 0 ? "+" : ""}
          {chg.toFixed(1)}%
        </span>
      </p>
      <p className="note">
        {t("funds.nav")}. {t("funds.nav.note")}
      </p>

      <menu className="fund-ranges" aria-label={t("funds.range")}>
        {RANGES.map((r) => (
          <button
            key={r}
            type="button"
            className="range"
            aria-pressed={r === range}
            onClick={() => setRange(r)}
          >
            {r}
          </button>
        ))}
      </menu>
      <Chart fund={fund} range={range} />

      <h2>{t("funds.returns")}</h2>
      {headline?.f != null ? (
        <p>
          {fill(t("funds.returns.say"), {
            y: String(headline.y),
            f: pct(headline.f),
            kind: t(`funds.${vs(headline.f, headline.k) ?? "level"}`),
            nifty: t(`funds.${vs(headline.f, headline.n) ?? "level"}`),
          })}
        </p>
      ) : null}
      <table className="ftable">
        <thead>
          <tr>
            <th />
            <th className="num">{t("funds.returns.fund")}</th>
            <th className="num">{t("funds.returns.kind")}</th>
            <th className="num">{t("funds.returns.nifty")}</th>
          </tr>
        </thead>
        <tbody>
          {m.rows.map((r) => (
            <tr key={r.y}>
              <th scope="row">{r.y}Y</th>
              <td className="num">{r.f == null ? t("funds.returns.young") : `${pct(r.f)}%`}</td>
              <td className="num">
                {pct(r.k)}% <Vs a={r.f} b={r.k} />
              </td>
              <td className="num">
                {pct(r.n)}% <Vs a={r.f} b={r.n} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>{t("funds.rolling")}</h2>
      {m.roll ? (
        <>
          <p>
            {fill(t("funds.rolling.say"), {
              median: pct(m.roll.median),
              min: pct(m.roll.min),
              max: pct(m.roll.max),
              pos: String(Math.round(m.roll.positive * 100)),
            })}
          </p>
          {m.beat != null ? (
            <p>{fill(t("funds.rolling.beat"), { n: String(Math.round(m.beat * 100)) })}</p>
          ) : null}
        </>
      ) : (
        <p className="note">{t("funds.rolling.none")}</p>
      )}

      <h2>{t("funds.falls")}</h2>
      <p className="note">{t("funds.falls.say")}</p>
      {m.falls.length ? (
        <table className="ftable">
          <thead>
            <tr>
              <th />
              <th className="num">{t("funds.falls.fund")}</th>
              <th className="num">{t("funds.falls.nifty")}</th>
            </tr>
          </thead>
          <tbody>
            {m.falls.map((f) => (
              <tr key={f.id}>
                <th scope="row">{t(`funds.falls.${f.id}`)}</th>
                <td className="num dn">{pct(f.fund, 0)}%</td>
                <td className="num">{f.bench == null ? "–" : `${pct(f.bench, 0)}%`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="note">{t("funds.falls.none")}</p>
      )}

      <div className="stats">
        <div className="stat">
          <span className="note">{t("funds.cost")}</span>
          <b className="num">{fund.cost.toFixed(2)}%</b>
          <span className="note">{fill(t("funds.cost.say"), { c: cost1000 })}</span>
        </div>
        <div className="stat">
          <span className="note">{t("funds.size")}</span>
          <b className="num">{fund.size == null ? "–" : `₹${inr(fund.size)} cr`}</b>
          <span className="note">
            {fund.size == null
              ? t("funds.size.none")
              : fill(t("funds.size.say"), { s: inr(fund.size) })}
          </span>
        </div>
      </div>

      <FundNote name={fund.name} />
      <Overlap name={fund.name} />

      <h2>{t("funds.buys")}</h2>
      {fund.lots.length ? (
        <ul className="buys">
          {fund.lots.map((l) => (
            <li key={l.acquired_on}>
              <span>{day(l.acquired_on)}</span>
              <span className="num">
                {l.quantity.toFixed(1)} {t("funds.buys.units")} · {money(l.cost)}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="note">{t("funds.buys.none")}</p>
      )}
      <p className="note">
        {t("funds.how")} {t("funds.sample")}
      </p>
    </article>
  );
}

export function FundsPane() {
  const t = useWords();
  const [q, setQ] = useState("");
  const items: Item[] = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return FUNDS.filter(
      (f) => !needle || `${f.name} ${f.amc} ${f.category}`.toLowerCase().includes(needle),
    )
      .sort((a, b) => Number(b.lots.length > 0) - Number(a.lots.length > 0))
      .map((f) => ({
        ...f,
        group: f.lots.length ? "held" : "all",
        groupLabel: f.lots.length ? t("funds.held") : t("funds.not.held"),
      }));
  }, [q, t]);
  return (
    <div className="funds">
      <label className="fund-search">
        <span className="visually-hidden">{t("funds.search")}</span>
        <input
          type="search"
          value={q}
          placeholder={t("funds.search.hint")}
          aria-label={t("funds.search")}
          onChange={(e) => setQ(e.target.value)}
        />
      </label>
      {items.length ? (
        <ListAndPane
          items={items}
          label={t("funds.list.label")}
          renderRow={(f) => (
            <>
              <span className="lp-name">
                <b>{f.name}</b>
                <span className="note">
                  {f.amc} · {f.category}
                </span>
              </span>
              <span className="num lp-price">{pct(cagr(f.series, 3) ?? cagr(f.series, 1))}%</span>
            </>
          )}
          renderPane={(f) => <FundPage fund={f} />}
        />
      ) : (
        <p className="pane-state empty">{t("funds.none")}</p>
      )}
    </div>
  );
}

const pane: Pane = { id: "funds", path: "/funds", titleKey: "funds.title", Component: FundsPane };
export default pane;
