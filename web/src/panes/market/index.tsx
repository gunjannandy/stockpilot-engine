// Market & news: ranked news cards with the stocks each affects, sector mood, coming up, big-fund money, exposure per holding.
import { useEffect, useState } from "react";
import type { Pane } from "../../areas";
import { money, pct } from "../../format";
import { useWords } from "../../words";
import { HOLDINGS, NEWS, type NewsItem, quote, stockById } from "../_kit/pending";
import { Toast } from "../_kit/Toast";
import { Spark, Tile, VChip } from "../_kit/ui";
import "./market.css";

const NIFTY = Array.from(
  { length: 120 },
  (_, i) => 24000 + i * 20 + Math.sin(i / 5) * 180 + Math.cos(i / 11) * 140,
);
const SECTORS = [
  { k: "Banks", v: 4.2 },
  { k: "IT", v: 2.1 },
  { k: "Consumer", v: 1.1 },
  { k: "Energy", v: -0.6 },
  { k: "Cement", v: -3.4 },
  { k: "Textiles", v: -2.8 },
];
const FLOWS = [
  { who: "Large fund house A", did: "bought", what: "Echo Bank", amt: "high" },
  { who: "Large fund house B", did: "sold", what: "Alpha Steel", amt: "medium" },
  { who: "Large fund house C", did: "bought", what: "Gamma Tech", amt: "medium" },
];
const COMING = [
  { d: "30 Nov", say: "Interest rate decision" },
  { d: "12 Dec", say: "Results: Harbor Ports, Indigo Cement" },
  { d: "19 Dec", say: "Monthly auto sales" },
];

function Tilelet({ id, dir, size }: { id: string; dir: "helps" | "hurts" | "none"; size: number }) {
  const t = useWords();
  const st = stockById(id);
  if (!st) return null;
  const q = quote(st);
  return (
    <div className="mk-tile">
      <div className="mk-tt">
        <b>{st.name}</b>
        <VChip v={st.verdict} />
      </div>
      <Spark closes={q.closes} />
      <div className="mk-tb">
        {dir === "none" ? (
          <span className="k-pill">{t("v3.sectorNews")}</span>
        ) : (
          <span className={dir === "helps" ? "up" : "dn"}>
            {dir === "helps" ? `▲ ${t("v3.helps")}` : `▼ ${t("v3.hurts")}`}
          </span>
        )}
        <span className={`num ${q.day >= 0 ? "up" : "dn"}`}>{pct(q.day)}</span>
        {dir !== "none" && <span className="k-note">{"●".repeat(size)}</span>}
      </div>
    </div>
  );
}

/** A top story: high impact, touches what we hold or watch. It stays here for 7 days whatever its age. */
function Top({ n, i }: { n: NewsItem; i: number }) {
  const t = useWords();
  return (
    <article className="mk-top card k-up k-lift" style={{ "--i": i } as React.CSSProperties}>
      <div className="mk-meta">
        <span className={`mk-kind kind-${n.kind}`}>{t(`v3.kind.${n.kind}`)}</span>
        <span className="k-note">
          {n.source} · {n.age}
        </span>
      </div>
      <h3>{n.title}</h3>
      <p className="k-note">{n.line}</p>
      <div className="mk-tiles">
        {n.hits.map((h) => (
          <Tilelet key={h.id} id={h.id} dir={h.dir} size={h.size} />
        ))}
      </div>
    </article>
  );
}

type Line = {
  id: string;
  hour: string;
  title: string;
  source: string;
  kind: NewsItem["kind"];
  age: string;
  hits: { id: string; dir: "helps" | "hurts" }[];
};
// Made-up stream for the prototype: what the 5 to 15 minute news collector would add through the day.
const STREAM: Line[] = [
  {
    id: "s1",
    hour: "09:00",
    title: "Echo Bank raises its fixed deposit rates",
    source: "Dalal Daily",
    kind: "wire",
    age: "18 min ago",
    hits: [{ id: "echo-bank", dir: "helps" }],
  },
  {
    id: "s2",
    hour: "09:00",
    title: "Auto sales slow in November, dealers say",
    source: "Street Notes",
    kind: "blog",
    age: "31 min ago",
    hits: [{ id: "bravo-motors", dir: "hurts" }],
  },
  {
    id: "s3",
    hour: "08:00",
    title: "Gamma Tech wins a three-year software order",
    source: "Exchange filing",
    kind: "filing",
    age: "1h ago",
    hits: [{ id: "gamma-tech", dir: "helps" }],
  },
  {
    id: "s4",
    hour: "08:00",
    title: "Power demand hits a record in the north",
    source: "Market Ledger",
    kind: "wire",
    age: "1h ago",
    hits: [{ id: "delta-power", dir: "helps" }],
  },
  {
    id: "s5",
    hour: "07:00",
    title: "Port volumes flat for the second month",
    source: "Market Ledger",
    kind: "wire",
    age: "2h ago",
    hits: [{ id: "harbor-ports", dir: "hurts" }],
  },
];
const ARRIVING: Line[] = [
  {
    id: "s0",
    hour: "09:00",
    title: "Cement prices cut again in the south",
    source: "Dalal Daily",
    kind: "wire",
    age: "just now",
    hits: [{ id: "indigo-cement", dir: "hurts" }],
  },
  {
    id: "s00",
    hour: "09:00",
    title: "Juno Finance board meets on 4 December",
    source: "Exchange filing",
    kind: "filing",
    age: "just now",
    hits: [{ id: "juno-finance", dir: "helps" }],
  },
];

function StreamRow({ l, fresh, i }: { l: Line; fresh: boolean; i: number }) {
  const t = useWords();
  return (
    <li
      className={`mk-row k-up${fresh ? " is-new" : ""}`}
      style={{ "--i": i } as React.CSSProperties}
    >
      <span className={`mk-kind kind-${l.kind}`}>{t(`v3.kind.${l.kind}`)}</span>
      <span className="mk-rt">
        <b>{l.title}</b>
        <span className="k-note">
          {l.source} · {l.age}
        </span>
      </span>
      <span className="mk-hits">
        {l.hits.map((h) => {
          const st = stockById(h.id);
          return st ? (
            <span key={h.id} className={`mk-hit ${h.dir === "helps" ? "up" : "dn"}`}>
              {h.dir === "helps" ? "▲" : "▼"} {st.name}
            </span>
          ) : null;
        })}
      </span>
    </li>
  );
}

function Latest({ f }: { f: (l: Line) => boolean }) {
  const t = useWords();
  const [shown, setShown] = useState<Line[]>(STREAM);
  const [waiting, setWaiting] = useState<Line[]>([]);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  // The prototype plays two arrivals a few seconds after opening, the way the collector adds them.
  useEffect(() => {
    const id = setTimeout(() => setWaiting(ARRIVING), 4000);
    return () => clearTimeout(id);
  }, []);
  const rows = shown.filter(f);
  const hours = [...new Set(rows.map((l) => l.hour))];
  return (
    <section className="mk-latest">
      <div className="mk-lh">
        <h2 className="k-eyebrow">{t("mk.latest")}</h2>
        {waiting.length ? (
          <button
            type="button"
            className="mk-newpill k-in"
            onClick={() => {
              setFresh(new Set(waiting.map((w) => w.id)));
              setShown([...waiting, ...shown]);
              setWaiting([]);
            }}
          >
            ↑ {t("mk.newN").replace("{n}", String(waiting.length))}
          </button>
        ) : null}
      </div>
      {hours.map((h) => (
        <div key={h} className="mk-hour">
          <span className="mk-hh num">{h}</span>
          <ul>
            {rows
              .filter((l) => l.hour === h)
              .map((l, i) => (
                <StreamRow key={l.id} l={l} fresh={fresh.has(l.id)} i={i} />
              ))}
          </ul>
        </div>
      ))}
      {rows.length === 0 ? <p className="k-note">{t("v2.noneHere")}</p> : null}
    </section>
  );
}

function Exposure() {
  const t = useWords();
  const rows = HOLDINGS.map((r) => {
    const hits = NEWS.flatMap((n) => n.hits.filter((h) => h.id === r.st.id && h.rel === "direct"));
    const score =
      hits.reduce((a, h) => a + (h.dir === "helps" ? 1 : -1) * h.size, 0) * (r.h.share / 100) * 100;
    return { r, score };
  }).filter((x) => x.score !== 0);
  return (
    <Tile title={t("v3.exposure")}>
      <p className="k-note">{t("v3.exposureP")}</p>
      {rows.map(({ r, score }) => (
        <div key={r.st.id} className="mk-exp">
          <span>{r.st.name}</span>
          <span className="mk-expbar" aria-hidden="true">
            <i
              className={`k-grow ${score >= 0 ? "up" : "dn"}`}
              style={{
                width: `${Math.min(50, Math.abs(score) * 4)}%`,
                [score >= 0 ? "left" : "right"]: "50%",
              }}
            />
          </span>
          <b className={`num ${score >= 0 ? "up" : "dn"}`}>
            {score >= 0 ? "+" : "−"}
            {Math.abs(score).toFixed(1)}
          </b>
        </div>
      ))}
    </Tile>
  );
}

function MarketScreen() {
  const t = useWords();
  const [f, setF] = useState<"all" | "mine" | "filing" | "wire">("all");
  const held = (id: string) => HOLDINGS.some((r) => r.st.id === id);
  const top = [...NEWS]
    .filter((n) => n.matters >= 80 && n.hits.some((h) => h.rel === "direct"))
    .sort((a, b) => b.matters - a.matters)
    .slice(0, 5);
  const test = {
    all: () => true,
    mine: (l: Line) => l.hits.some((h) => held(h.id)),
    filing: (l: Line) => l.kind === "filing",
    wire: (l: Line) => l.kind !== "filing",
  } as const;
  return (
    <section className="mk">
      <header className="k-head">
        <p className="k-eyebrow">{t("v2.market")}</p>
        <h1>{t("v3.marketLine")}</h1>
        <p className="k-note">{t("v3.every15")}</p>
      </header>
      <div className="mk-grid">
        <div className="mk-main">
          <div className="mk-lh">
            <h2 className="k-eyebrow">{t("mk.top")}</h2>
            <span className="k-note">{t("mk.topP")}</span>
          </div>
          <div className="mk-tops">
            {top.map((n, i) => (
              <Top key={n.id} n={n} i={i} />
            ))}
          </div>
          <div className="k-chips mk-filter">
            {(["all", "mine", "filing", "wire"] as const).map((k) => (
              <button
                key={k}
                type="button"
                className="k-chipbtn"
                aria-pressed={f === k}
                onClick={() => setF(k)}
              >
                {t(`v3.nf.${k}`)}
              </button>
            ))}
          </div>
          <Latest f={test[f]} />
        </div>
        <aside className="mk-side">
          <Tile title={t("v3.marketToday")}>
            <div className="mk-nifty">
              <span>Nifty 50</span>
              <b className="num up">26,182 {pct(0.4)}</b>
            </div>
            <Spark closes={NIFTY} />
            <p>{t("v3.steady")}</p>
          </Tile>
          <Tile title={t("v3.sectorMood")}>
            <p className="k-note">{t("v2.mSect")}</p>
            {SECTORS.map((s) => (
              <div key={s.k} className="mk-exp">
                <span>{s.k}</span>
                <span className="mk-expbar" aria-hidden="true">
                  <i
                    className={`k-grow ${s.v >= 0 ? "up" : "dn"}`}
                    style={{
                      width: `${Math.abs(s.v) * 10}%`,
                      [s.v >= 0 ? "left" : "right"]: "50%",
                    }}
                  />
                </span>
                <b className={`num ${s.v >= 0 ? "up" : "dn"}`}>{pct(s.v)}</b>
              </div>
            ))}
          </Tile>
          <Tile title={t("v2.mFlows")}>
            <ul className="k-ul mk-flows">
              {FLOWS.map((f) => (
                <li key={f.what}>
                  {f.who} <b>{t(`v3.${f.did}`)}</b> {f.what}{" "}
                  <span className="k-pill">{t(`v3.amt.${f.amt}`)}</span>
                </li>
              ))}
            </ul>
          </Tile>
          <Tile title={t("v2.mEvents")}>
            {COMING.map((c) => (
              <div key={c.d} className="mk-coming">
                <b>{c.d}</b>
                <span>{c.say}</span>
              </div>
            ))}
          </Tile>
          <Exposure />
          <Tile title={t("v3.howOrder")}>
            <ol className="mk-order">
              {["o1", "o2", "o3", "o4", "o5"].map((k) => (
                <li key={k}>{t(`v3.${k}`)}</li>
              ))}
            </ol>
          </Tile>
        </aside>
      </div>
      <Toast />
      <p className="k-sample">{t("v2.proto")}</p>
    </section>
  );
}
const pane: Pane = {
  id: "market",
  path: "/market",
  titleKey: "shell.nav.market",
  Component: MarketScreen,
};
export default pane;
export { money };
