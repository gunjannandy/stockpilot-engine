// The stock's page, wired to the API (R6): header and price, chart, our call with its reasoning, facts and
// news, each a <Pane> with its own read, so one failing read never blanks the rest. Holding, key numbers and
// similar companies are not wired yet: they stay behind their banner until their own release.
import {
  type CallView,
  type ChartResponse,
  callSentences,
  type FactsResponse,
  type StockNewsResponse,
  type StockResponse,
  screenRoutes,
} from "@stockpilot/contract";
import { StockChart } from "../../charts/StockChart";
import type { Ohlc } from "../../charts/series";
import { money, pct } from "../../format";
import { Banner, Pane } from "../../panekit";
import { getLang } from "../../theme/theme";
import { useWords } from "../../words";

const atClose = (day: string) => `${day}T15:30:00+05:30`;
const dash = "—";

/** The contract's verdict word to the screen's chip class and word. "No view yet" has none. */
export function verdictKey(v: string): "sell" | "weak" | "buy" | "keep" | "watch" | null {
  switch (v) {
    case "Sell":
      return "sell";
    case "Weak":
    case "Trim":
      return "weak";
    case "Buy":
      return "buy";
    case "Hold":
      return "keep";
    case "Watch":
      return "watch";
    default:
      return null;
  }
}

/** The call to show: the newest day's, shortest horizon first. null when there is none. */
export function pickCall(calls: CallView[]): CallView | null {
  const day = calls.reduce((m, c) => (c.made_on > m ? c.made_on : m), "");
  return (
    calls.filter((c) => c.made_on === day).sort((a, b) => a.horizon_days - b.horizon_days)[0] ??
    null
  );
}

export function barsOfChart(c: ChartResponse): Ohlc[] {
  return c.d.map((time, i) => {
    const close = c.c[i] as number;
    return {
      time,
      open: c.o[i] ?? close,
      high: c.h[i] ?? close,
      low: c.l[i] ?? close,
      close,
      volume: c.v[i] ?? 0,
    };
  });
}

function Head({ symbol }: { symbol: string }) {
  const t = useWords();
  return (
    <Pane<StockResponse>
      id="stock-head"
      title={symbol}
      route={screenRoutes.stock}
      params={{ symbol }}
      updatedAt={(d) => d.quote?.at ?? (d.last ? atClose(d.last.date) : null)}
      windowHours={30}
      isEmpty={(d) => !d.known}
    >
      {(d) => {
        const price = d.quote?.price ?? d.last?.close ?? null;
        const prev = d.quote?.prev_close ?? d.last?.prev_close ?? null;
        const day = price !== null && prev ? (price / prev - 1) * 100 : null;
        return (
          <header className="sk-head">
            <div className="sk-hl">
              <h3>{d.entry?.name ?? d.symbol}</h3>
              <p className="note">
                {d.symbol}
                {d.entry ? ` · ${d.entry.exchange}` : ""}
              </p>
            </div>
            <div className="sk-hr">
              {price === null ? (
                <p className="note">{t("stock.d.noPrice")}</p>
              ) : (
                <>
                  <p className="px num">{money(price)}</p>
                  {day === null ? null : (
                    <p className="sk-pl">
                      <span className={day >= 0 ? "up" : "dn"}>
                        {pct(day)} {t("stock.today")}
                      </span>
                    </p>
                  )}
                </>
              )}
            </div>
          </header>
        );
      }}
    </Pane>
  );
}

function ChartSec({ symbol }: { symbol: string }) {
  const t = useWords();
  return (
    <Pane<ChartResponse>
      id="stock-chart"
      title={t("stock.chartH")}
      route={screenRoutes.stockChart}
      params={{ symbol }}
      updatedAt={(d) => (d.d.length ? atClose(d.d[d.d.length - 1] as string) : null)}
      windowHours={30}
    >
      {(d) =>
        d.c.length === 0 ? (
          <div className="pane-state empty" data-testid="stock-chart-none">
            <p>{t("stock.skNoChart")}</p>
            <p className="note">{t("stock.d.noChartP")}</p>
          </div>
        ) : (
          <StockChart bars={barsOfChart(d)} call={null} trades={[]} />
        )
      }
    </Pane>
  );
}

function Levels({ c }: { c: CallView }) {
  const t = useWords();
  const rows: [string, number | null][] = [
    [t("v2.riseTo"), c.could_rise_to],
    [t("v2.wouldBuy"), c.would_buy_at],
    [t("v2.fallTo"), c.sell_at_once_at],
  ];
  return (
    <dl className="k-kv k-callkv">
      {rows.map(([k, v]) => (
        <div key={k} className="k-row">
          <dt>{k}</dt>
          <dd className="num">{v === null ? dash : money(v, 0)}</dd>
        </div>
      ))}
    </dl>
  );
}

function CallBody({ calls }: { calls: CallView[] }) {
  const t = useWords();
  const lang = getLang();
  const c = pickCall(calls);
  const v = c ? verdictKey(c.verdict) : null;
  if (!c || v === null || c.chance === null)
    return (
      <p className="pane-state empty" data-testid="stock-call-none">
        {t("stock.d.noCall")}
      </p>
    );
  const chance = Math.round(c.chance * 100);
  const sentences = callSentences(c.sentences_json);
  const conf = c.confidence ? c.confidence[lang] : null;
  return (
    <div className="k-call">
      <p>
        <span className={`chip v-${v}`}>{t(`stock.verdict.${v}`)}</span>{" "}
        <b className="num">{chance}%</b> <span>{t("v2.chanceCap")}</span>
        {c.limited ? (
          <span className="k-pill worse" title={t("v2.rzLimitedTip")}>
            {" "}
            {t("v2.rzLimited")}
          </span>
        ) : null}
      </p>
      {conf ? <p className="k-conf">{conf}</p> : null}
      {c.base_rate !== null ? (
        <p className="k-note">
          {t("stock.d.base")
            .replace("{n}", String(c.base_cases))
            .replace("{p}", String(Math.round(c.base_rate * 100)))
            .replace("{d}", String(c.horizon_days))}
        </p>
      ) : null}
      {sentences.length ? (
        <ul className="k-ul" data-testid="stock-call-why">
          {sentences.map((s) => (
            <li key={s.key}>{s[lang] || s.en}</li>
          ))}
        </ul>
      ) : null}
      <Levels c={c} />
      <p className="note">{t("stock.d.madeOn").replace("{day}", c.made_on)}</p>
    </div>
  );
}

function CallSec({ symbol }: { symbol: string }) {
  const t = useWords();
  return (
    <Pane
      id="stock-call"
      title={t("v2.ourView")}
      route={screenRoutes.stockCalls}
      params={{ symbol }}
      updatedAt={(d: { calls: CallView[] }) => {
        const c = pickCall(d.calls);
        return c ? atClose(c.made_on) : null;
      }}
      windowHours={48}
    >
      {(d: { calls: CallView[] }) => <CallBody calls={d.calls} />}
    </Pane>
  );
}

type Facts = NonNullable<FactsResponse["facts"]>;
function FactsBody({ f }: { f: Facts }) {
  const t = useWords();
  const lang = getLang();
  const n = (v: number | null, f2: (x: number) => string) => (v === null ? dash : f2(v));
  const rows: { k: string; v: string; sector?: string }[] = [
    {
      k: t("v2.fPe"),
      v: n(f.pe, (x) => x.toFixed(1)),
      sector: n(f.pe_sector, (x) => x.toFixed(1)),
    },
    { k: t("stock.d.pb"), v: n(f.pb, (x) => x.toFixed(1)) },
    { k: t("stock.d.dy"), v: n(f.dividend_yield_pct, (x) => `${x.toFixed(1)}%`) },
    { k: t("stock.d.cap"), v: n(f.market_cap_cr, (x) => `₹${x.toLocaleString("en-IN")} Cr`) },
    { k: t("stock.d.sales"), v: n(f.sales_growth_yoy_pct, (x) => pct(x)) },
    { k: t("stock.d.profit"), v: n(f.profit_growth_yoy_pct, (x) => pct(x)) },
    { k: t("v2.fRoe"), v: n(f.roe_pct, (x) => `${x.toFixed(1)}%`) },
    { k: t("stock.d.roce"), v: n(f.roce_pct, (x) => `${x.toFixed(1)}%`) },
    { k: t("v2.fDe"), v: n(f.debt_to_equity, (x) => x.toFixed(2)) },
    { k: t("v2.ownHold"), v: n(f.promoter_pct, (x) => `${x.toFixed(1)}%`) },
    { k: t("v2.ownPledge"), v: n(f.pledge_pct, (x) => `${x.toFixed(1)}%`) },
  ];
  return (
    <>
      <div className="k-scroll">
        <table className="k-table k-raw">
          <thead>
            <tr>
              <th>{t("v3.kn.num")}</th>
              <th className="r">{t("v3.kn.this")}</th>
              <th className="r">{t("v3.kn.sector")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.k}>
                <td>{r.k}</td>
                <td className="r num">
                  <b>{r.v}</b>
                </td>
                <td className="r num">{r.sector ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {f.sentences.length ? (
        <ul className="k-ul" data-testid="stock-facts-say">
          {f.sentences.map((s) => (
            <li key={s.key}>{s[lang] || s.en}</li>
          ))}
        </ul>
      ) : null}
      {f.figures.length ? (
        <details>
          <summary>{t("panes.how")}</summary>
          <ul className="k-ul">
            {f.figures.map((g) => (
              <li key={`${g.metric}:${g.period}`}>
                {g.metric}: <span className="num">{g.value}</span> · {g.period} · {g.source}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </>
  );
}

function FactsSec({ symbol }: { symbol: string }) {
  const t = useWords();
  return (
    <Pane<FactsResponse>
      id="stock-facts"
      title={t("v2.facts")}
      route={screenRoutes.stockFacts}
      params={{ symbol }}
      updatedAt={(d) => d.as_of}
      windowHours={24 * 40}
      isEmpty={(d) => d.facts === null}
    >
      {(d) => (d.facts ? <FactsBody f={d.facts} /> : null)}
    </Pane>
  );
}

function NewsSec({ symbol }: { symbol: string }) {
  const t = useWords();
  const lang = getLang();
  return (
    <Pane<StockNewsResponse>
      id="stock-news"
      title={t("v2.newsL")}
      route={screenRoutes.stockNews}
      params={{ symbol }}
      updatedAt={(d) => d.news[0]?.impact.judged_at ?? null}
      windowHours={36}
      isEmpty={(d) => d.news.length === 0}
    >
      {(d) => (
        <ul className="k-ul k-newslist">
          {d.news.map((n) => (
            <li key={n.id} className="k-news">
              <span className="k-newsrel">
                {n.impact.sector_only || n.impact.direction === null ? (
                  <span className="k-pill">{t("v3.sectorNews")}</span>
                ) : (
                  <span
                    className={`k-pill ${n.impact.direction === "good" ? "better" : n.impact.direction === "bad" ? "worse" : ""}`}
                  >
                    {n.impact.direction === "good"
                      ? `▲ ${t("v3.helps")}`
                      : n.impact.direction === "bad"
                        ? `▼ ${t("v3.hurts")}`
                        : t("stock.d.mixed")}
                  </span>
                )}
              </span>
              <span>
                <a href={n.link} target="_blank" rel="noreferrer noopener">
                  <b>{n.title}</b>
                </a>
                <span className="k-note"> {n.source}</span>
                {!n.impact.sector_only && (lang === "bn" ? n.impact.why_bn : n.impact.why_en) ? (
                  <span className="k-note">
                    {" "}
                    · {lang === "bn" ? n.impact.why_bn : n.impact.why_en}
                  </span>
                ) : null}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Pane>
  );
}

/** Sections whose data is not wired yet: shown as their banner, with the section's name above. */
function Pending({ id, title }: { id: string; title: string }) {
  return (
    <section className="sk-sec k-sec">
      <h3>{title}</h3>
      <Banner id={`stock-${id}`} whole={false} />
    </section>
  );
}

export function StockDetail({ symbol }: { symbol: string }) {
  const t = useWords();
  const sym = symbol.toUpperCase();
  return (
    <article className="sk" data-testid="stock-detail">
      <Head symbol={sym} />
      <ChartSec symbol={sym} />
      <CallSec symbol={sym} />
      <FactsSec symbol={sym} />
      <NewsSec symbol={sym} />
      <Pending id="holding" title={t("v2.yourHold")} />
      <Pending id="similar" title={t("v3.similar")} />
    </article>
  );
}
