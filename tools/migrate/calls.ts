// Calls map: v2's calls (the D1 table of today's views and the vault's whole history) become v3's append-only
// `calls` rows. A v2 row carries a 3 and a 6 month chance; v3 has one row per horizon (63 and 126 trading days),
// id `exchange:symbol:day:horizon`. The call keeps its v2 date (`as_of`) so screens say "as of" that day.
// v2 had no base-rate cases or past-case counts, so they are 0 and the row says so in `model_version`.
// Fund calls go to the registry's `fund_calls` dataset; only rows with a 3-year quartile can be carried.
import type { AreaMap, Mapped, Row } from "./core/types";
import { dayOf, exchange, ist, num, parse } from "./core/util";

const VERDICT: Record<string, string> = {
  buy: "Buy",
  hold: "Hold",
  sell: "Sell",
  wait: "Watch",
  trim: "Trim",
  weak: "Weak",
};
const HORIZONS = [
  { days: 63, key: "3m" },
  { days: 126, key: "6m" },
] as const;

type Reason = { text?: unknown };
const sentences = (form: unknown, bn: string) => {
  const f = (form ?? {}) as Record<string, unknown>;
  const out: { key: string; en: string; bn: string }[] = [];
  const add = (key: string, list: unknown) => {
    if (Array.isArray(list))
      for (const r of list as Reason[])
        if (r && typeof r.text === "string" && r.text) out.push({ key, en: r.text, bn: "" });
  };
  add("v2_for", f.reasons_for);
  add("v2_against", f.reasons_against);
  add("v2_change", f.what_would_change);
  if (bn && out[0]) out[0].bn = bn;
  else if (bn) out.push({ key: "v2_summary", en: "", bn });
  return out;
};

/** One v2 call row to its v3 rows (one per horizon that has a chance; one "No view yet" row when none has). */
export function callRows(r: Row): Mapped[] {
  const form = parse(r.form) as Record<string, unknown> | null;
  const made = dayOf(r.as_of ?? r.written_at);
  const sym = String(r.symbol);
  const ex = exchange(r.exchange);
  const verdict = VERDICT[String(r.call)] ?? "No view yet";
  const bn = String(((form?.bengali ?? {}) as Record<string, unknown>).summary ?? "");
  const mk = (h: (typeof HORIZONS)[number], chance: number | null, v: string): Mapped => ({
    dataset: "calls",
    row: {
      id: `${ex}:${sym}:${made}:${h.days}`,
      symbol: sym,
      exchange: ex,
      made_on: made,
      verdict: v,
      chance,
      horizon_days: h.days,
      base_cases: 0,
      base_rate: null,
      sell_line: num(r[`low_${h.key}`]) ?? 0,
      buy_line: num(r[`high_${h.key}`]) ?? 0,
      could_rise_to: num(r[`high_${h.key}`]),
      would_buy_at: null,
      sell_at_once_at: null,
      limited: 0,
      sentences_json: JSON.stringify(sentences(form, bn)),
      similar_n: 0,
      similar_beat: 0,
      model_version: `v2:${r.model ?? "unknown"}`,
    },
  });
  const rows = HORIZONS.flatMap((h) => {
    const c = num(r[`chance_${h.key}`]);
    return c === null ? [] : [mk(h, c, verdict)];
  });
  return rows.length ? rows : [mk(HORIZONS[0], null, "No view yet")];
}

const quartile = (r: Row): number | null => {
  const q = num(r.quartile);
  if (q !== null && q >= 1 && q <= 4) return Math.trunc(q);
  const rank = num(r.rank);
  const of = num(r.of ?? r.ranked);
  return rank !== null && of ? Math.min(4, Math.max(1, Math.ceil((rank / of) * 4))) : null;
};

const map: AreaMap = {
  area: "calls",
  tables: {
    "d1:calls": { datasets: ["calls"], map: callRows },
    "vault:calls": { datasets: ["calls"], map: callRows },
    "vault:fund_calls": {
      datasets: ["fund_calls"],
      map: (r) => {
        const q = quartile(r);
        const id = String(r.id ?? r.fund_id ?? "");
        const call = r.call === "buy" || r.call === "watch" ? r.call : null;
        if (!id || q === null) return null;
        return {
          dataset: "fund_calls",
          row: {
            id,
            kind: r.kind === "track" ? "track" : "call",
            name: String(r.name ?? r.fund_name ?? id),
            category: r.category ?? null,
            call: r.kind === "track" ? null : call,
            rank: num(r.rank),
            of: num(r.of ?? r.ranked),
            quartile: q,
            chance: num(r.chance),
            cases: num(r.cases),
            periods: num(r.periods),
            avg_excess: num(r.avg_excess),
            reasons: String(r.reasons ?? ""),
            caveat: String(r.caveat ?? ""),
            as_of: dayOf(r.as_of ?? r.written_at ?? ist(r.at)),
          },
        };
      },
    },
  },
};
export default map;
