import { useEffect, useMemo, useRef, useState } from "react";
import type { Pane } from "../../areas";
import { StockChart } from "../../charts/StockChart";
import { useWords } from "../../words";
import "./stock.css";
import {
  callFor,
  history,
  openLinks,
  type SampleStock,
  STOCKS,
  sparkPath,
  type Verdict,
} from "./sample";

const ORDER: Verdict[] = ["sell", "weak", "buy", "keep", "watch"];
const inr0 = (v: number) =>
  `₹${v.toLocaleString("en-IN", { maximumFractionDigits: v < 1000 ? 1 : 0 })}`;

function Spark({ closes }: { closes: number[] }) {
  const s = sparkPath(closes);
  return (
    <svg
      className={`sp ${s.up ? "up" : "dn"}`}
      viewBox="0 0 100 30"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <path className="a" d={s.area} />
      <path className="l" d={s.line} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function Meter({ v }: { v: number }) {
  const t = useWords();
  const tone = v >= 62 ? "strong" : v >= 40 ? "fair" : "weak";
  return (
    <span className="sk-mt">
      <span className="sk-mtr">
        <i style={{ left: `${Math.min(96, Math.max(4, v))}%` }} />
      </span>
      <span className={`sk-mw t-${tone}`}>{t(`stock.meter.${tone}`)}</span>
    </span>
  );
}

function OpenIn({ st }: { st: SampleStock }) {
  const t = useWords();
  const [open, setOpen] = useState(false);
  const l = openLinks(st);
  return (
    <span className="sk-lyr">
      <button
        type="button"
        className="sk-btn"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <path
            d="M14 3v2h3.6l-9.8 9.8 1.4 1.4L19 6.4V10h2V3h-7ZM5 5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-6h-2v6H5V7h6V5H5Z"
            fill="currentColor"
          />
        </svg>
        {t("stock.openIn")}
      </button>
      {open && (
        <div className="sk-menu">
          <a className="sk-mi" href={l.kite} target="_blank" rel="noreferrer noopener">
            {t("stock.kite")}
          </a>
          <a className="sk-mi" href={l.screener} target="_blank" rel="noreferrer noopener">
            {t("stock.screener")}
          </a>
        </div>
      )}
    </span>
  );
}

function Detail({ st, bars }: { st: SampleStock; bars: ReturnType<typeof history> }) {
  const t = useWords();
  const last = bars[bars.length - 1]?.close ?? 0;
  const prev = bars[bars.length - 2]?.close ?? last;
  const day = (last / prev - 1) * 100;
  const call = useMemo(() => callFor(last, st.verdict), [last, st.verdict]);
  const age =
    st.ageSeconds < 90
      ? t("stock.live").replace("{n}", String(st.ageSeconds))
      : t("stock.liveMin").replace("{n}", String(Math.round(st.ageSeconds / 60)));
  return (
    <article className="sk">
      <header className="sk-head">
        <div className="sk-hl">
          <span className={`chip v-${st.verdict}`}>{t(`stock.verdict.${st.verdict}`)}</span>
          <h2>{st.name}</h2>
          <p className="note">
            {st.symbol} · {st.sector} · {st.exchange}
          </p>
        </div>
        <div className="sk-hr">
          <p className="px num">{inr0(last)}</p>
          <p className="sk-pl">
            <span className={day >= 0 ? "up" : "dn"}>
              {day >= 0 ? "+" : "−"}
              {Math.abs(day).toFixed(1)}% {t("stock.today")}
            </span>{" "}
            · {age}
          </p>
        </div>
      </header>
      <div className="sk-acts">
        <button type="button" className="sk-btn sk-tonal">
          ＋ {t("stock.watchAdd")}
        </button>
      </div>
      <section className="sk-sec">
        <div className="sk-sh">
          <span className="sk-ic" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="22" height="22">
              <title>chart</title>
              <path d="m3 17 6-6 4 4 7-8-1.4-1.4L13 12.2l-4-4-7 7L3 17Z" fill="currentColor" />
            </svg>
          </span>
          <div className="sk-stt">
            <h3>{t("stock.chartH")}</h3>
            <p>{t("stock.chartP")}</p>
          </div>
        </div>
        <StockChart bars={bars} call={call} trades={st.trades} extra={<OpenIn st={st} />} />
      </section>
    </article>
  );
}

export function StockPane() {
  const t = useWords();
  const [sel, setSel] = useState(
    () => new URLSearchParams(window.location.search).get("s") ?? STOCKS[0]?.id,
  );
  const [q, setQ] = useState("");
  const [full, setFull] = useState(
    () => new URLSearchParams(window.location.search).has("s") && window.innerWidth < 700,
  );
  const data = useMemo(() => new Map(STOCKS.map((s) => [s.id, history(s)])), []);
  const listRef = useRef<HTMLDivElement>(null);
  const items = STOCKS.filter((s) =>
    (s.name + s.symbol).toLowerCase().includes(q.toLowerCase()),
  ).sort((a, b) => ORDER.indexOf(a.verdict) - ORDER.indexOf(b.verdict));
  const cur = STOCKS.find((s) => s.id === sel) ?? STOCKS[0];

  const choose = (id: string, open = false) => {
    setSel(id);
    if (open) setFull(true);
    const u = new URL(window.location.href);
    u.searchParams.set("s", id);
    window.history.replaceState({}, "", u);
  };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA")) return;
      if (e.key === "Escape") setFull(false);
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      const i = items.findIndex((x) => x.id === cur?.id);
      const n =
        items[Math.max(0, Math.min(items.length - 1, i + (e.key === "ArrowDown" ? 1 : -1)))];
      if (n) {
        e.preventDefault();
        choose(n.id);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  let lastV: Verdict | null = null;
  return (
    <div className="sk-lp" data-full={full ? "pane" : "list"}>
      <nav className="sk-list" ref={listRef} aria-label={t("stock.list")}>
        <label className="sk-qf">
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
            <path
              d="M15.5 14h-.8l-.3-.3A6.5 6.5 0 1 0 14 15.5l.3.3v.8l5 5 1.5-1.5-5-5Zm-6 0a4.5 4.5 0 1 1 0-9 4.5 4.5 0 0 1 0 9Z"
              fill="currentColor"
            />
          </svg>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t("stock.filter")}
            autoComplete="off"
          />
        </label>
        {items.map((s) => {
          const head = s.verdict !== lastV;
          lastV = s.verdict;
          const closes = (data.get(s.id) ?? []).slice(-130).map((b) => b.close);
          const price = closes[closes.length - 1] ?? 0;
          return (
            <div key={s.id}>
              {head && (
                <div className={`lgh r-${s.verdict}`}>
                  <b>{t(`stock.group.${s.verdict}`)}</b>
                  <span className="n num">
                    {items.filter((x) => x.verdict === s.verdict).length}
                  </span>
                </div>
              )}
              <button
                type="button"
                className={`lrow r-${s.verdict}`}
                aria-current={cur?.id === s.id ? "true" : undefined}
                onClick={() => choose(s.id, true)}
              >
                <span className={`chip v-${s.verdict}`}>{t(`stock.verdict.${s.verdict}`)}</span>
                <span className="lm">
                  <b className="trunc">{s.name}</b>
                  <span className="ls trunc">
                    {s.symbol} · {s.sector}
                  </span>
                </span>
                <span className="lspc">
                  <Spark closes={closes} />
                </span>
                <span className="lr num">
                  {inr0(price)}
                  <Meter v={s.strength} />
                </span>
              </button>
            </div>
          );
        })}
      </nav>
      <aside className="sk-pane">
        <button type="button" className="sk-back" onClick={() => setFull(false)}>
          ← {t("stock.back")}
        </button>
        {cur && <Detail st={cur} bars={data.get(cur.id) ?? []} />}
      </aside>
    </div>
  );
}

const pane: Pane = { id: "stock", path: "/stock", titleKey: "stock.title", Component: StockPane };
export default pane;
