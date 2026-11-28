// Market & news: ranked news cards with the stocks each affects, sector mood, coming up, big-fund money, exposure per holding.
import type { Pane } from "../../areas";
import { useWords } from "../../words";
import { HOLDINGS, money, NEWS, type NewsItem, pct, quote, stockById } from "../_kit/data";
import { Toast } from "../_kit/Toast";
import { Spark, Tile, VChip } from "../_kit/ui";
import "./market.css";

const RANK = { filing: 0, wire: 1, blog: 2 } as const;
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

function Card({ n }: { n: NewsItem }) {
  const t = useWords();
  const held = n.hits.filter((h) => HOLDINGS.some((r) => r.st.id === h.id)).length;
  const touches = n.hits.some(
    (h) => stockById(h.id)?.verdict === "buy" || stockById(h.id)?.verdict === "sell",
  );
  const hue = (n.id.charCodeAt(1) * 47) % 360;
  return (
    <article className="mk-card card k-in">
      <div
        className="mk-img"
        style={{
          background: `linear-gradient(135deg, hsl(${hue} 55% 78%), hsl(${(hue + 60) % 360} 50% 66%))`,
        }}
        role="img"
        aria-label={t("v3.preview")}
      >
        {n.source.slice(0, 1)}
      </div>
      <div className="mk-body">
        <div className="mk-meta">
          <b>
            {t("v3.matters")} {n.matters}
          </b>
          <span className="k-bar-h mk-m" aria-hidden="true">
            <i style={{ width: `${n.matters}%` }} />
          </span>
          <span className="k-note">
            {n.matters >= 80 ? t("v3.high") : t("v3.normal")} · {n.age}
          </span>
          <span className={`k-pill kind-${n.kind}`}>{t(`v3.kind.${n.kind}`)}</span>
          <span className="k-pill mk-src">{n.source}</span>
        </div>
        <h3>{n.title}</h3>
        <p>{n.line}</p>
        <div className="mk-tiles">
          {n.hits.map((h) => (
            <Tilelet key={h.id} id={h.id} dir={h.dir} size={h.size} />
          ))}
        </div>
        <div className="k-chips mk-chips">
          {held > 0 && (
            <span className="k-pill better">
              {t("v2.youHoldT")} {held}
            </span>
          )}
          <span className="k-pill">
            {n.kind === "filing" ? `1 ${t("v3.source")}` : `3 ${t("v3.sources")}`}
          </span>
          <span className="k-pill">{n.age}</span>
          {touches && <span className="k-pill">{t("v3.touchesCall")}</span>}
        </div>
      </div>
    </article>
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
              className={score >= 0 ? "up" : "dn"}
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
  const ranked = [...NEWS].sort((a, b) => RANK[a.kind] - RANK[b.kind] || b.matters - a.matters);
  const mine = [
    ...new Set(NEWS.flatMap((n) => n.hits.filter((h) => h.rel === "direct").map((h) => h.id))),
  ];
  return (
    <section className="mk">
      <header className="k-head">
        <h1>{t("v2.market")}</h1>
        <p>{t("v3.marketLine")}</p>
        <p className="k-note">{t("v3.every15")}</p>
      </header>
      <div className="mk-grid">
        <div className="mk-main">
          <h2 className="k-eyebrow">{t("v3.yourNews")}</h2>
          <div className="mk-mine">
            {mine.map((id) => {
              const h = NEWS.flatMap((n) => n.hits).find((x) => x.id === id);
              return h ? <Tilelet key={id} id={id} dir={h.dir} size={h.size} /> : null;
            })}
          </div>
          {ranked.map((n) => (
            <Card key={n.id} n={n} />
          ))}
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
                    className={s.v >= 0 ? "up" : "dn"}
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
