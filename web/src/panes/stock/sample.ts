// Made-up prototype data: a seeded random walk, never real prices or real holdings.
import type { Bar } from "../../charts/series";

export type SampleStock = {
  id: string;
  name: string;
  symbol: string;
  sector: string;
  exchange: string;
  seed: number;
  start: number;
  buys: string[];
  ageSeconds: number;
};

export const STOCKS: SampleStock[] = [
  {
    id: "gamma-tech",
    name: "Gamma Tech",
    symbol: "GAMMATECH",
    sector: "IT",
    exchange: "NSE",
    seed: 7,
    start: 900,
    buys: ["2025-06-12", "2026-02-03"],
    ageSeconds: 20,
  },
  {
    id: "echo-bank",
    name: "Echo Bank",
    symbol: "ECHOBANK",
    sector: "Banks",
    exchange: "NSE",
    seed: 6,
    start: 1200,
    buys: ["2025-09-18"],
    ageSeconds: 45,
  },
  {
    id: "foxtrot-foods",
    name: "Foxtrot Foods",
    symbol: "FOXFOODS",
    sector: "Consumer",
    exchange: "BSE",
    seed: 1,
    start: 2400,
    buys: [],
    ageSeconds: 300,
  },
  {
    id: "harbor-ports",
    name: "Harbor Ports",
    symbol: "HARBOR",
    sector: "Transport",
    exchange: "NSE",
    seed: 8,
    start: 700,
    buys: ["2025-12-01"],
    ageSeconds: 20,
  },
];

function rng(seed: number) {
  let s = seed * 2654435761;
  return () => {
    s = (s ^ (s << 13)) >>> 0;
    s = (s ^ (s >>> 17)) >>> 0;
    s = (s ^ (s << 5)) >>> 0;
    return s / 4294967296;
  };
}

export function history(st: SampleStock, last = "2026-11-27", years = 5): Bar[] {
  const r = rng(st.seed);
  const out: Bar[] = [];
  const d = new Date(`${last}T00:00:00Z`);
  d.setUTCFullYear(d.getUTCFullYear() - years);
  let p = st.start;
  while (d.toISOString().slice(0, 10) <= last) {
    const dow = d.getUTCDay();
    if (dow !== 0 && dow !== 6) {
      p = Math.max(20, p * (1 + (r() - 0.48) * 0.03));
      out.push({ time: d.toISOString().slice(0, 10), close: +p.toFixed(2) });
    }
    d.setUTCDate(d.getUTCDate() + 1);
  }
  return out;
}

/** Where each "Open in" link points: the instrument itself, never a search page. */
export function openLinks(st: Pick<SampleStock, "symbol" | "exchange">) {
  const ex = st.exchange === "BSE" ? "BSE" : "NSE";
  return {
    kite: `https://kite.zerodha.com/chart/ext/tvc/${ex}/${encodeURIComponent(st.symbol)}/0`,
    screener: `https://www.screener.in/company/${encodeURIComponent(st.symbol)}/`,
  };
}
