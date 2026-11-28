// The stock page's v2 sections, rebuilt for v3: changed band, call card, numbers in plain words, holding, news, similar companies.
import { useMemo, useState } from "react";
import { useWords } from "../../words";
import { Analyse } from "./Analyse";
import {
  barsOf,
  type CallCardData,
  callCard,
  facts,
  HOLDINGS,
  money,
  type NewsItem,
  newsFor,
  pct,
  quote,
  RS,
  type SampleStock,
  similar,
  stockById,
} from "./data";
import { Icon, Sec, VChip } from "./ui";
import { useWatch, watch } from "./watch";

const fill = (s: string, v: Record<string, string | number>) =>
  s.replace(/\{(\w+)\}/g, (_, k) => String(v[k] ?? ""));

export function Actions({ st }: { st: SampleStock }) {
  const t = useWords();
  const w = useWatch();
  const on = w.star.has(st.id);
  return (
    <div className="sk-acts">
      <button
        type="button"
        className="sk-btn sk-tonal"
        aria-pressed={on}
        onClick={() => watch.toggleStar(st.id, t("v2.added"), t("v2.removed"))}
      >
        {on ? `★ ${t("v2.inWl")}` : `＋ ${t("v2.addWl")}`}
      </button>
      <button
        type="button"
        className="sk-btn"
        onClick={() => watch.set("snooze", st.id, true, t("v2.snoozed"))}
      >
        {t("v2.snooze")}
      </button>
      <button
        type="button"
        className="sk-btn"
        onClick={() => watch.set("never", st.id, true, t("v2.dismissed"))}
      >
        {t("v2.dismiss")}
      </button>
    </div>
  );
}

export function ChangedBand({ st }: { st: SampleStock }) {
  const t = useWords();
  const w = useWatch();
  const c = callCard(st).changed;
  if (!c || w.seen.has(st.id)) return null;
  return (
    <div className="k-band k-in">
      <i className="k-dot" />
      <b>{c}</b>
      <button type="button" className="k-link" onClick={() => watch.markSeen([st.id])}>
        {t("v2.gotIt")}
      </button>
    </div>
  );
}

function ChanceBar({ c }: { c: number }) {
  const t = useWords();
  return (
    <div className="k-chance">
      <div className="k-chance-top">
        <b className="num k-chance-n">{c}%</b>
        <span>{t("v2.chanceCap")}</span>
      </div>
      <div className="k-chance-bar" aria-hidden="true">
        <span className="z sell" />
        <span className="z mid" />
        <span className="z buy" />
        <i style={{ left: `${c}%` }} />
      </div>
      <div className="k-chance-lines">
        <span>{t("v2.sellBelow")}</span>
        <span>{t("v2.buyAbove")}</span>
      </div>
    </div>
  );
}

function Row({ k, children }: { k: string; children: React.ReactNode }) {
  return (
    <>
      <dt>{k}</dt>
      <dd>{children}</dd>
    </>
  );
}

export function CallSec({ st }: { st: SampleStock }) {
  const t = useWords();
  const c: CallCardData = callCard(st);
  const q = quote(st);
  return (
    <Sec
      icon="call"
      title={t("v2.ourView")}
      sub={t(`v3.verdictLine.${st.verdict}`)}
      aside={<VChip v={st.verdict} />}
    >
      <ChanceBar c={c.chance} />
      <Analyse what={st.name} />
      <p className="k-conf">
        {fill(t("v3.confidence"), { n: c.track.n, b: c.track.beat })}
        {c.limited ? (
          <span className="k-pill worse" title={t("v2.rzLimitedTip")}>
            {t("v2.rzLimited")}
          </span>
        ) : null}
      </p>
      <p className="k-note">{fill(t("v3.base"), { n: c.base, h: c.horizon })}</p>
      <dl className="k-kv k-callkv">
        <Row k={t("v2.why")}>{c.why}</Row>
        <Row k={t("v2.whatWrong")}>
          <ul className="k-ul">
            {c.risks.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </Row>
        <Row k={t("v2.money")}>{c.ifYouAct}</Row>
        <Row k={t("v2.taxL")}>{c.tax}</Row>
        <Row k={t("v2.wouldBuy")}>{c.buyIf}</Row>
        <Row k={t("v2.fallTo")}>{c.sellIf}</Row>
        <Row k={t("v2.riseTo")}>{c.couldRise}</Row>
      </dl>
      <section className="k-ladder" aria-label={t("v2.ladder")}>
        <h4 className="k-eyebrow">{t("v2.ladder")}</h4>
        {[
          { l: t("v2.riseTo"), v: q.last * (st.verdict === "sell" ? 1.0 : 1.12), c: "up" },
          { l: t("v2.now"), v: q.last, c: "now" },
          { l: t("v2.wouldBuy"), v: q.last * 0.93, c: "buy" },
          { l: t("v2.fallTo"), v: q.last * 0.91, c: "dn" },
        ].map((r) => (
          <div key={r.l} className={`k-rung ${r.c}`}>
            <span>{r.l}</span>
            <b className="num">{money(r.v, 0)}</b>
          </div>
        ))}
      </section>
    </Sec>
  );
}

function Bars({ vals, label }: { vals: number[]; label: string }) {
  const hi = Math.max(...vals.map(Math.abs), 1);
  const bars = vals.map((v, i) => ({ id: `q${i}`, v }));
  return (
    <div className="k-qbars" role="img" aria-label={label}>
      {bars.map((b) => (
        <i
          key={b.id}
          className={b.v < 0 ? "dn" : "up"}
          style={{ height: `${Math.max(8, (Math.abs(b.v) / hi) * 100)}%` }}
        />
      ))}
    </div>
  );
}

export function FactsSec({ st }: { st: SampleStock }) {
  const t = useWords();
  const names: Record<string, string> = {
    pe: "v2.fPe",
    roe: "v2.fRoe",
    debt: "v2.fDe",
    growth: "v2.fGr",
    swing: "v2.fVol",
    fall: "v2.fDd",
    trading: "v2.fAdv",
  };
  const q = quote(st);
  const lo = Math.min(...q.closes);
  const hi = Math.max(...q.closes);
  const at = ((q.last - lo) / (hi - lo || 1)) * 100;
  const seed = st.seed;
  const sales = Array.from({ length: 8 }, (_, i) => 60 + Math.sin(seed + i) * 14 + i * 3);
  const profit = Array.from({ length: 8 }, (_, i) => 8 + Math.cos(seed * 2 + i) * 9 + i * 0.6);
  return (
    <Sec icon="facts" title={t("v2.facts")} sub={t("v2.compare")}>
      <div className="k-facts">
        {facts(st).map((f) => (
          <div className="k-fact" key={f.id}>
            <span className="k-eyebrow">{t(names[f.id] ?? "")}</span>
            <div className="v num">
              {f.value} <span className={`k-pill ${f.better}`}>{t(`v3.vs.${f.better}`)}</span>
            </div>
            <p>{f.sentence}</p>
            <details>
              <summary>{t("panes.how")}</summary>
              <p>{f.how}</p>
            </details>
          </div>
        ))}
      </div>
      <div className="k-more">
        <div>
          <h4 className="k-eyebrow">{t("v2.xRange")}</h4>
          <span className="k-range" aria-hidden="true">
            <i style={{ left: `${at}%` }} />
          </span>
          <p className="k-note num">
            {money(lo, 0)} – {money(hi, 0)}
          </p>
        </div>
        <div>
          <h4 className="k-eyebrow">{t("v2.xVolS")}</h4>
          <p className="k-big num">{(0.8 + (seed % 5) * 0.4).toFixed(1)}×</p>
          <p className="k-note">{t("v3.volUsual")}</p>
        </div>
        <div>
          <h4 className="k-eyebrow">{t("v2.xDelivery")}</h4>
          <p className="k-big num">{40 + (seed % 6) * 5}%</p>
        </div>
        <div>
          <h4 className="k-eyebrow">{t("v2.ownT")}</h4>
          <p className="k-note">
            {t("v2.ownHold")} <b className="num">{38 + (seed % 9) * 4}%</b> · {t("v2.ownPledge")}{" "}
            <b className="num">{seed % 4}%</b>
          </p>
        </div>
        <div>
          <h4 className="k-eyebrow">{t("v2.xSales")}</h4>
          <Bars vals={sales} label={t("v2.xSales")} />
        </div>
        <div>
          <h4 className="k-eyebrow">{t("v2.xProfit")}</h4>
          <Bars
            vals={profit.map((v, i) => (i === 2 && seed % 3 === 0 ? -v / 2 : v))}
            label={t("v2.xProfit")}
          />
        </div>
        <div>
          <h4 className="k-eyebrow">{t("v3.results")}</h4>
          <p className="k-big">{["12 Dec", "5 Jan", "19 Jan", "2 Feb"][seed % 4]}</p>
        </div>
      </div>
    </Sec>
  );
}

export function HoldingSec({ st }: { st: SampleStock }) {
  const t = useWords();
  const h = HOLDINGS.find((r) => r.st.id === st.id)?.h ?? null;
  return (
    <Sec icon="hold" title={t("v2.yourHold")} sub={h ? undefined : t("v3.notHeld")}>
      {h ? (
        <>
          <dl className="k-kv">
            <Row k={t("v2.hQty")}>
              <b className="num">{h.qty}</b> · {h.account}
            </Row>
            <Row k={t("v2.hVal")}>
              <b className="num">{money(h.value, 0)}</b>
            </Row>
            <Row k={t("v2.hGainL")}>
              <b className={`num ${h.gain >= 0 ? "up" : "dn"}`}>
                {money(h.gain, 0)} ({pct(h.gainPct)})
              </b>
            </Row>
            <Row k={t("v2.hShareL")}>
              <b className="num">{h.share.toFixed(1)}%</b>
            </Row>
            <Row k={t("v2.hTaxL")}>{h.tax}</Row>
          </dl>
          <div className="k-scroll">
            <table className="k-table">
              <thead>
                <tr>
                  <th>{t("v2.lots")}</th>
                  <th className="r">{t("v2.lotQ")}</th>
                  <th className="r">{t("v2.lotC")}</th>
                  <th>{t("v2.lotLT")}</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>{h.bought}</td>
                  <td className="r num">{h.qty}</td>
                  <td className="r num">{money(h.cost, 0)}</td>
                  <td>{h.ltFrom}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </>
      ) : null}
    </Sec>
  );
}

function NewsLine({ n, st }: { n: NewsItem; st: SampleStock }) {
  const t = useWords();
  const hit = n.hits.find((h) => h.id === st.id);
  return (
    <li className="k-news">
      <span className="k-newsrel">
        {hit?.rel === "sector" ? (
          <span className="k-pill">{t("v3.sectorNews")}</span>
        ) : (
          <span className={`k-pill ${hit?.dir === "helps" ? "better" : "worse"}`}>
            {hit?.dir === "helps" ? `▲ ${t("v3.helps")}` : `▼ ${t("v3.hurts")}`}
          </span>
        )}
      </span>
      <span>
        <b>{n.title}</b>
        <span className="k-note">
          {" "}
          {n.source} · {n.age}
        </span>
      </span>
    </li>
  );
}

export function NewsSec({ st }: { st: SampleStock }) {
  const t = useWords();
  const list = newsFor(st);
  return (
    <Sec icon="news" title={t("v2.newsL")} sub={list.length ? undefined : t("v3.noNews")}>
      {list.length ? (
        <ul className="k-ul k-newslist">
          {list.map((n) => (
            <NewsLine key={n.id} n={n} st={st} />
          ))}
        </ul>
      ) : null}
    </Sec>
  );
}

export function PeersSec({ st, onPick }: { st: SampleStock; onPick: (id: string) => void }) {
  const t = useWords();
  return (
    <Sec icon="peers" title={t("v3.similar")} sub={t("v3.similarP")}>
      <div className="k-grid c3">
        {similar(st).map((p) => (
          <button key={p.id} type="button" className="k-peer" onClick={() => onPick(p.id)}>
            <VChip v={p.verdict} />
            <b>{p.name}</b>
            <span className="k-note">
              {p.sector} · {money(quote(p).last)}
            </span>
          </button>
        ))}
      </div>
    </Sec>
  );
}

export { stockById, RS, Icon };

/** The raw numbers behind the chart: one row a day, newest first, to copy or download. */
export function RawSec({ st }: { st: SampleStock }) {
  const t = useWords();
  const [n, setN] = useState(15);
  const rows = useMemo(() => [...barsOf(st)].reverse(), [st]);
  const shown = rows.slice(0, n);
  const csv = () => {
    const head = "date,open,high,low,close,volume";
    const body = rows.map((b) => [b.time, b.open, b.high, b.low, b.close, b.volume].join(","));
    const url = URL.createObjectURL(new Blob([[head, ...body].join("\n")], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${st.symbol}-daily.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <Sec
      icon="facts"
      title={t("v3.rawH")}
      sub={t("v3.rawP")}
      aside={
        <button type="button" className="sk-btn" onClick={csv}>
          {t("v3.rawCsv")}
        </button>
      }
    >
      <div className="k-scroll">
        <table className="k-table k-raw">
          <thead>
            <tr>
              <th>{t("v3.rawDate")}</th>
              <th className="r">{t("v3.rawOpen")}</th>
              <th className="r">{t("v3.rawHigh")}</th>
              <th className="r">{t("v3.rawLow")}</th>
              <th className="r">{t("v3.rawClose")}</th>
              <th className="r">{t("v3.rawChg")}</th>
              <th className="r">{t("v3.rawVol")}</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((b, i) => {
              const prev = rows[i + 1]?.close ?? b.open;
              const ch = (b.close / prev - 1) * 100;
              return (
                <tr key={b.time}>
                  <td className="num">{b.time}</td>
                  <td className="r num">{b.open.toFixed(2)}</td>
                  <td className="r num">{b.high.toFixed(2)}</td>
                  <td className="r num">{b.low.toFixed(2)}</td>
                  <td className="r num">{b.close.toFixed(2)}</td>
                  <td className={`r num ${ch >= 0 ? "up" : "dn"}`}>{pct(ch, 2)}</td>
                  <td className="r num">{b.volume.toLocaleString("en-IN")}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {n < rows.length ? (
        <button type="button" className="sk-btn" onClick={() => setN(n + 30)}>
          {t("v3.rawMore")}
        </button>
      ) : null}
      <p className="k-note">{t("v3.rawNeeds")}</p>
    </Sec>
  );
}
