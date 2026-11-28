// Made-up prototype data (invented names, seeded random walks). Never real prices or holdings.
import type { Call, Ohlc } from "../../charts/series";

export type Verdict = "sell" | "weak" | "buy" | "keep" | "watch";
export type Trade = { date: string; kind: "buy" | "sell"; qty: number };
export type SampleStock = {
  id: string;
  name: string;
  symbol: string;
  sector: string;
  exchange: "NSE" | "BSE";
  verdict: Verdict;
  strength: number; // 0..100 for the Strong / Fair / Weak meter
  seed: number;
  start: number;
  drift: number;
  trades: Trade[];
  ageSeconds: number;
};

const S = (
  name: string,
  symbol: string,
  sector: string,
  exchange: "NSE" | "BSE",
  verdict: Verdict,
  strength: number,
  seed: number,
  start: number,
  drift: number,
  trades: Trade[],
  ageSeconds = 20,
): SampleStock => ({
  id: name.toLowerCase().replace(/\W+/g, "-"),
  name,
  symbol,
  sector,
  exchange,
  verdict,
  strength,
  seed,
  start,
  drift,
  trades,
  ageSeconds,
});

export const STOCKS: SampleStock[] = [
  S("Alpha Steel", "ALPHASTL", "Metals", "NSE", "sell", 18, 3, 600, -0.0002, [
    { date: "2025-04-10", kind: "buy", qty: 40 },
    { date: "2026-09-02", kind: "sell", qty: 10 },
  ]),
  S("Bravo Motors", "BRAVOMOT", "Auto", "NSE", "sell", 26, 5, 1700, -0.0003, [
    { date: "2025-08-21", kind: "buy", qty: 15 },
  ]),
  S("Cedar Pharma", "CEDARPH", "Health", "BSE", "weak", 38, 2, 800, 0.0001, []),
  S("Delta Power", "DELTAPWR", "Energy", "NSE", "weak", 42, 4, 220, 0.0002, [
    { date: "2025-11-12", kind: "buy", qty: 100 },
  ]),
  S("Echo Bank", "ECHOBANK", "Banks", "NSE", "buy", 74, 6, 1100, 0.0007, [
    { date: "2025-09-18", kind: "buy", qty: 20 },
  ]),
  S("Foxtrot Foods", "FOXFOODS", "Consumer", "BSE", "buy", 66, 1, 2200, 0.0005, [], 300),
  S("Gamma Tech", "GAMMATECH", "IT", "NSE", "buy", 82, 7, 900, 0.0008, [
    { date: "2025-06-12", kind: "buy", qty: 12 },
    { date: "2026-02-03", kind: "buy", qty: 8 },
  ]),
  S("Harbor Ports", "HARBOR", "Transport", "NSE", "keep", 55, 8, 700, 0.0004, [
    { date: "2025-12-01", kind: "buy", qty: 30 },
  ]),
  S("Indigo Cement", "INDIGOCM", "Materials", "NSE", "keep", 52, 9, 2900, 0.0002, []),
  S("Juno Finance", "JUNOFIN", "Finance", "BSE", "keep", 58, 10, 600, 0.0003, [
    { date: "2026-03-15", kind: "buy", qty: 25 },
  ]),
  S("Kilo Retail", "KILORTL", "Retail", "NSE", "keep", 48, 11, 450, 0.0001, []),
  S("Lima Telecom", "LIMATEL", "Telecom", "NSE", "watch", 60, 12, 1700, 0.0004, []),
];

function rng(seed: number) {
  let s = (seed * 2654435761) >>> 0;
  return () => {
    s = (s ^ (s << 13)) >>> 0;
    s = (s ^ (s >>> 17)) >>> 0;
    s = (s ^ (s << 5)) >>> 0;
    return s / 4294967296;
  };
}

export const LAST = "2026-11-27";

export function history(st: SampleStock, years = 6): Ohlc[] {
  const r = rng(st.seed);
  const out: Ohlc[] = [];
  const d = new Date(`${LAST}T00:00:00Z`);
  d.setUTCFullYear(d.getUTCFullYear() - years);
  let p = st.start;
  while (d.toISOString().slice(0, 10) <= LAST) {
    if (d.getUTCDay() % 6 !== 0) {
      const open = p;
      p = Math.max(20, p * (1 + st.drift + (r() - 0.5) * 0.024));
      const hi = Math.max(open, p) * (1 + r() * 0.012);
      const lo = Math.min(open, p) * (1 - r() * 0.012);
      out.push({
        time: d.toISOString().slice(0, 10),
        open: +open.toFixed(2),
        high: +hi.toFixed(2),
        low: +lo.toFixed(2),
        close: +p.toFixed(2),
        volume: Math.round(200000 + r() * 900000 * (1 + Math.abs(p / open - 1) * 30)),
      });
    }
    d.setUTCDate(d.getUTCDate() + 1);
  }
  return out;
}

export function callFor(last: number, verdict: Verdict): Call {
  const up = verdict === "buy" ? 1.04 : verdict === "sell" ? 0.97 : 1;
  const mid = (m: number) => +(last * up ** m).toFixed(2);
  const w = (m: number, k: number) => 0.04 * Math.sqrt(m) * k;
  const lo = (m: number) => +(mid(m) * (1 - w(m, 1.28))).toFixed(2);
  const hi = (m: number) => +(mid(m) * (1 + w(m, 1.28))).toFixed(2);
  return {
    low: [lo(1), lo(3), lo(6)],
    likely: [mid(1), mid(3), mid(6)],
    high: [hi(1), hi(3), hi(6)],
  };
}

/** Where each "Open in" link points: the instrument itself, never a search page. */
export function openLinks(st: Pick<SampleStock, "symbol" | "exchange">) {
  return {
    kite: `https://kite.zerodha.com/chart/ext/tvc/${st.exchange}/${encodeURIComponent(st.symbol)}/0`,
    screener: `https://www.screener.in/company/${encodeURIComponent(st.symbol)}/`,
  };
}

/** The small coloured line each list row carries. */
export function sparkPath(closes: number[]) {
  const lo = Math.min(...closes);
  const hi = Math.max(...closes);
  const W = 100;
  const H = 30;
  const x = (i: number) => 2 + ((W - 4) * i) / (closes.length - 1);
  const y = (v: number) => 3 + (H - 6) * (1 - (v - lo) / (hi - lo || 1));
  const p = closes.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join("");
  return {
    line: p,
    area: `${p}L${x(closes.length - 1)} ${H}L${x(0)} ${H}Z`,
    up: (closes[closes.length - 1] ?? 0) >= (closes[0] ?? 0),
  };
}
