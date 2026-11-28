// Market & news: the indices, then news cards by time with the stocks each story touches (/api/news).
// Sector mood, big-fund money and exposure per holding sit behind their own banners (`banner.market.<section>`)
// and say so plainly until their data lands. News is ordered by time; ranking by impact comes with the model.
import { type NewsCard, type NewsResponse, screenRoutes } from "@stockpilot/contract";
import type { Pane as PaneDef } from "../../areas";
import { Bannered, IndicesStrip, Pane } from "../../panekit";
import { useWords } from "../../words";
import "./market.css";

const IST_MS = 5.5 * 3600_000;
const pad = (n: number) => String(n).padStart(2, "0");

/** A time as IST text parts, or null when it cannot be read. */
export function istParts(t: string): { day: string; hour: string; stamp: string } | null {
  const ms = Date.parse(t);
  if (Number.isNaN(ms)) return null;
  const d = new Date(ms + IST_MS);
  const day = d.toISOString().slice(0, 10);
  const hh = pad(d.getUTCHours());
  const mm = pad(d.getUTCMinutes());
  return { day, hour: `${hh}:00`, stamp: `${day}T${hh}:${mm}:00+05:30` };
}

/** Newest first; a card whose time cannot be read goes last, never dropped. */
export function byTime(items: NewsCard[]): NewsCard[] {
  const at = (c: NewsCard) => {
    const ms = Date.parse(c.published_at);
    return Number.isNaN(ms) ? Number.NEGATIVE_INFINITY : ms;
  };
  return [...items].sort((a, b) => at(b) - at(a) || a.id.localeCompare(b.id));
}

const KIND: Record<number, string> = { 3: "filing", 2: "wire", 1: "blog" };

function Impact({ i }: { i: NewsCard["impacts"][number] }) {
  const t = useWords();
  const bn = t("mk.lang") === "bn";
  if (i.sector_only)
    return (
      <li className="mk-hit">
        <span className="k-pill">{t("v3.sectorNews")}</span> {i.symbol}
      </li>
    );
  const dir = i.direction;
  const why = (bn ? i.why_bn : i.why_en) || (bn ? i.why_en : i.why_bn);
  return (
    <li className={`mk-hit ${dir === "good" ? "up" : dir === "bad" ? "dn" : ""}`}>
      <b>
        {dir === "good" ? "▲" : dir === "bad" ? "▼" : "◆"} {i.symbol}
      </b>{" "}
      <span className="k-note">
        {t(`mk.dir.${dir ?? "mixed"}`)} · {t(`mk.size.${i.size}`)}
        {why ? ` · ${why}` : ""}
      </span>
    </li>
  );
}

function Card({ c }: { c: NewsCard }) {
  const t = useWords();
  const when = istParts(c.published_at);
  return (
    <li className="mk-row" data-testid="news-card">
      <span className={`mk-kind kind-${KIND[c.weight]}`}>{t(`v3.kind.${KIND[c.weight]}`)}</span>
      <span className="mk-rt">
        <a href={c.link} target="_blank" rel="noopener noreferrer">
          <b>{c.title}</b>
        </a>
        <span className="k-note">
          {c.source}
          {when ? ` · ${when.stamp.slice(11, 16)}` : ""}
          {c.source_count > 1 ? ` · ${t("mk.sources").replace("{n}", String(c.source_count))}` : ""}
        </span>
        {c.impacts.length ? (
          <ul className="k-ul mk-hits">
            {c.impacts.map((i) => (
              <Impact key={i.id} i={i} />
            ))}
          </ul>
        ) : null}
      </span>
    </li>
  );
}

function Latest({ items }: { items: NewsCard[] }) {
  const t = useWords();
  const rows = byTime(items);
  const groups: { key: string; day: string; hour: string; cards: NewsCard[] }[] = [];
  for (const c of rows) {
    const p = istParts(c.published_at);
    const key = p ? `${p.day} ${p.hour}` : "unknown";
    const last = groups[groups.length - 1];
    if (last && last.key === key) last.cards.push(c);
    else groups.push({ key, day: p?.day ?? "", hour: p?.hour ?? "–", cards: [c] });
  }
  return (
    <section className="mk-latest">
      {groups.map((g) => (
        <div key={g.key} className="mk-hour">
          <span className="mk-hh num">
            {g.day ? `${g.day.slice(8)}/${g.day.slice(5, 7)} ` : ""}
            {g.hour}
          </span>
          <ul>
            {g.cards.map((c) => (
              <Card key={c.id} c={c} />
            ))}
          </ul>
        </div>
      ))}
      <p className="k-note">{t("v3.every15")}</p>
    </section>
  );
}

function News() {
  const t = useWords();
  return (
    <Pane<NewsResponse>
      id="news"
      title={t("mk.latest")}
      route={screenRoutes.news}
      updatedAt={(d) => {
        const ms = Math.max(...d.items.map((c) => Date.parse(c.published_at)));
        return Number.isFinite(ms) ? istParts(new Date(ms).toISOString())?.stamp : null;
      }}
      windowHours={24}
      isEmpty={(d) => d.items.length === 0}
    >
      {(d) => <Latest items={d.items} />}
    </Pane>
  );
}

/** A section that has no data source yet: behind its own banner flag, and honest when it is on. */
function Later({ section, title, body }: { section: string; title: string; body: string }) {
  return (
    <Bannered screen="market" section={section}>
      <section className="pane" data-pane={`market-${section}`}>
        <h2>{title}</h2>
        <p className="pane-state empty" data-testid={`market-${section}-empty`}>
          {body}
        </p>
      </section>
    </Bannered>
  );
}

function MarketScreen() {
  const t = useWords();
  return (
    <section className="mk">
      <header className="k-head">
        <p className="k-eyebrow">{t("v2.market")}</p>
        <h1>{t("mk.title")}</h1>
        <p className="k-note">{t("mk.sub")}</p>
      </header>
      <div className="mk-grid">
        <div className="mk-main">
          <News />
        </div>
        <aside className="mk-side">
          <IndicesStrip />
          <Later section="sector" title={t("v3.sectorMood")} body={t("mk.sectorLater")} />
          <Later section="funds" title={t("v2.mFlows")} body={t("mk.fundsLater")} />
          <Later section="exposure" title={t("v3.exposure")} body={t("mk.exposureLater")} />
        </aside>
      </div>
    </section>
  );
}

const pane: PaneDef = {
  id: "market",
  path: "/market",
  titleKey: "shell.nav.market",
  Component: MarketScreen,
};
export default pane;
