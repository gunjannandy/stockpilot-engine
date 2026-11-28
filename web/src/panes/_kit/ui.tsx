// Shared v3 prototype pieces: the list row, the meter, the sparkline, the section heading, the segmented switch.
import { type ReactNode, useEffect, useState } from "react";
import { useWords } from "../../words";
import { sparkPath } from "../stock/sample";
import { callCard, type Change, money, quote, type SampleStock } from "./data";
import "./kit.css";

export function Spark({ closes }: { closes: number[] }) {
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

export function Meter({ v }: { v: number }) {
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

/** A change as numbers: the call before and after (when it moved) and the chance before and after. */
export function ChangeText({ c }: { c: Change }) {
  const t = useWords();
  return (
    <span className="k-chg num">
      {c.from !== c.to ? (
        <>
          {t(`stock.verdict.${c.from}`)}→{t(`stock.verdict.${c.to}`)} ·{" "}
        </>
      ) : null}
      {c.was}→{c.now}%
    </span>
  );
}

export function VChip({ v }: { v: string }) {
  const t = useWords();
  return <span className={`chip v-${v}`}>{t(`stock.verdict.${v}`)}</span>;
}

const ICONS: Record<string, string> = {
  chart: "m3 17 6-6 4 4 7-8-1.4-1.4L13 12.2l-4-4-7 7L3 17Z",
  call: "M12 2 1 21h22L12 2Zm1 15h-2v-2h2v2Zm0-4h-2V9h2v4Z",
  facts: "M4 4h16v2H4V4Zm0 7h16v2H4v-2Zm0 7h10v2H4v-2Z",
  hold: "M20 6h-4V4a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2H4a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2ZM10 4h4v2h-4V4Z",
  news: "M4 5h13v14H5a1 1 0 0 1-1-1V5Zm15 3h1a1 1 0 0 1 1 1v8a2 2 0 0 1-2 2V8ZM7 8h7v2H7V8Zm0 4h7v2H7v-2Z",
  peers:
    "M16 11a3 3 0 1 0-3-3 3 3 0 0 0 3 3Zm-8 0a3 3 0 1 0-3-3 3 3 0 0 0 3 3Zm0 2c-2.3 0-7 1.2-7 3.5V19h14v-2.5C15 14.2 10.3 13 8 13Zm8 0c-.3 0-.6 0-1 .1 1.2.8 2 2 2 3.4V19h6v-2.5c0-2.3-4.700-3.500-7-3.500Z",
  star: "m12 17.3 6.2 3.700-1.600-7L22 9.200l-7.200-.6L12 2 9.200 8.600 2 9.200 7.400 14l-1.600 7 6.200-3.700Z",
};
export function Icon({ name }: { name: keyof typeof ICONS | string }) {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
      <path d={ICONS[name] ?? ICONS.chart} fill="currentColor" />
    </svg>
  );
}

/** An open section: icon, bold heading, one plain sentence, then its content. No card, no tab. */
export function Sec({
  icon,
  title,
  sub,
  children,
  aside,
}: {
  icon: string;
  title: string;
  sub?: string;
  children: ReactNode;
  aside?: ReactNode;
}) {
  return (
    <section className="sk-sec k-sec">
      <div className="sk-sh">
        <span className="sk-ic" aria-hidden="true">
          <Icon name={icon} />
        </span>
        <div className="sk-stt">
          <h3>{title}</h3>
          {sub ? <p>{sub}</p> : null}
        </div>
        {aside}
      </div>
      {children}
    </section>
  );
}

export function Seg<T extends string>({
  value,
  onChange,
  options,
  label,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { id: T; label: string; n?: number }[];
  label: string;
}) {
  return (
    <div className="k-seg" role="tablist" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.id}
          type="button"
          role="tab"
          aria-selected={value === o.id}
          onClick={() => onChange(o.id)}
        >
          {o.label}
          {o.n !== undefined ? <span className="k-n num">{o.n}</span> : null}
        </button>
      ))}
    </div>
  );
}

export function Tile({
  title,
  children,
  wide,
}: {
  title: string;
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <section className={`k-tile card${wide ? " wide" : ""}`}>
      <h2 className="k-eyebrow">{title}</h2>
      {children}
    </section>
  );
}

export function StockRow({
  st,
  active,
  onClick,
  reasons,
  mark,
  star,
}: {
  st: SampleStock;
  active?: boolean;
  onClick?: () => void;
  reasons?: ReactNode;
  mark?: boolean;
  star?: ReactNode;
}) {
  const q = quote(st);
  return (
    <div className="k-lrowwrap">
      <button
        type="button"
        className={`lrow r-${st.verdict}${mark ? " is-changed" : ""}`}
        aria-current={active ? "true" : undefined}
        onClick={onClick}
      >
        <VChip v={st.verdict} />
        <span className="lm">
          <b className="trunc">
            {mark ? <i className="k-dot" role="img" aria-label="changed" /> : null}
            {st.name}
          </b>
          <span className="ls trunc">
            {mark && callCard(st).changed ? (
              <ChangeText c={callCard(st).changed as Change} />
            ) : (
              <>
                {st.symbol} · {st.sector}
              </>
            )}
          </span>
          {reasons}
        </span>
        <span className="lspc">
          <Spark closes={q.closes} />
        </span>
        <span className="lr num">
          {money(q.last)}
          <Meter v={st.strength} />
        </span>
      </button>
      {star}
    </div>
  );
}

/** The Table view every list page shares: sortable by clicking a heading, one row per stock. */
export function StockTable({
  rows,
  onPick,
  cols,
}: {
  rows: SampleStock[];
  onPick: (id: string) => void;
  cols?: ("sector" | "pe" | "growth")[];
}) {
  const t = useWords();
  const [sort, setSort] = useState<{ k: string; dir: 1 | -1 }>({ k: "chance", dir: -1 });
  const val = (s: SampleStock, k: string) =>
    k === "name"
      ? s.name
      : k === "chance"
        ? s.strength
        : k === "price"
          ? quote(s).last
          : k === "day"
            ? quote(s).day
            : k === "pe"
              ? 8 + ((s.seed * 7) % 30)
              : k === "growth"
                ? ((s.seed * 11) % 40) - 8
                : s.sector;
  const sorted = [...rows].sort((a, b) => {
    const x = val(a, sort.k);
    const y = val(b, sort.k);
    return (x > y ? 1 : x < y ? -1 : 0) * sort.dir;
  });
  const th = (k: string, label: string, right = false) => (
    <th
      className={right ? "r" : ""}
      aria-sort={sort.k === k ? (sort.dir === 1 ? "ascending" : "descending") : "none"}
    >
      <button
        type="button"
        className="k-th"
        onClick={() => setSort({ k, dir: sort.k === k ? (sort.dir === 1 ? -1 : 1) : -1 })}
      >
        {label}
        {sort.k === k ? (sort.dir === 1 ? " ▲" : " ▼") : ""}
      </button>
    </th>
  );
  const c = cols ?? ["sector", "pe", "growth"];
  return (
    <div className="k-scroll card k-tablewrap">
      <table className="k-table">
        <thead>
          <tr>
            {th("name", t("v3.colStock"))}
            <th>{t("v3.colView")}</th>
            {th("chance", t("v3.colChance"), true)}
            {th("price", t("v3.colPrice"), true)}
            {th("day", t("v3.colToday"), true)}
            {c.includes("sector") && th("sector", t("v3.colSector"))}
            {c.includes("pe") && th("pe", t("v3.colPe"), true)}
            {c.includes("growth") && th("growth", t("v3.colGrowth"), true)}
          </tr>
        </thead>
        <tbody>
          {sorted.map((s) => {
            const q = quote(s);
            return (
              <tr key={s.id} className="k-tr" onClick={() => onPick(s.id)}>
                <td>
                  <b>{s.name}</b> <span className="k-note">{s.symbol}</span>
                </td>
                <td>
                  <VChip v={s.verdict} />
                </td>
                <td className="r num">{s.strength}%</td>
                <td className="r num">{money(q.last)}</td>
                <td className={`r num ${q.day >= 0 ? "up" : "dn"}`}>
                  {q.day >= 0 ? "+" : "−"}
                  {Math.abs(q.day).toFixed(1)}%
                </td>
                {c.includes("sector") && <td>{s.sector}</td>}
                {c.includes("pe") && <td className="r num">{val(s, "pe")}</td>}
                {c.includes("growth") && <td className="r num">{val(s, "growth")}%</td>}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** One open group on a long page: a heading, one plain sentence, then its content. It rises in as it scrolls into view. */
export function Group({
  id,
  title,
  sub,
  children,
  aside,
}: {
  id: string;
  title: string;
  sub?: string;
  children: ReactNode;
  aside?: ReactNode;
}) {
  return (
    <section className="k-group" id={`g-${id}`} aria-labelledby={`g-${id}-h`}>
      <header className="k-group-h">
        <div>
          <h2 id={`g-${id}-h`}>{title}</h2>
          {sub ? <p>{sub}</p> : null}
        </div>
        {aside}
      </header>
      {children}
    </section>
  );
}

/** A sticky row of jump links for a long page. The link of the group in view is marked. */
export function GroupNav({
  items,
  label,
}: {
  items: { id: string; label: string }[];
  label: string;
}) {
  const [on, setOn] = useState(items[0]?.id ?? "");
  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(
      (es) => {
        for (const e of es) if (e.isIntersecting) setOn(e.target.id.replace(/^g-/, ""));
      },
      { rootMargin: "-20% 0px -70% 0px" },
    );
    for (const i of items) {
      const el = document.getElementById(`g-${i.id}`);
      if (el) io.observe(el);
    }
    return () => io.disconnect();
  }, [items]);
  return (
    <nav className="k-gnav" aria-label={label}>
      {items.map((i) => (
        <a
          key={i.id}
          href={`#g-${i.id}`}
          aria-current={on === i.id ? "true" : undefined}
          onClick={(e) => {
            e.preventDefault();
            setOn(i.id);
            document.getElementById(`g-${i.id}`)?.scrollIntoView({
              behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
                ? "auto"
                : "smooth",
              block: "start",
            });
          }}
        >
          {i.label}
        </a>
      ))}
    </nav>
  );
}
