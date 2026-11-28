// Stand-ins for the sample data the screens used to draw. There is no data in here: every list is empty and
// every per-stock function answers "nothing yet", so a screen shows its empty state until its own session
// wires it to a real route. Delete each import as you wire a pane (see web/src/panes/README.md), and this
// file when none remain. Shapes below are what the approved layouts were drawn with, not the contract.
import type { Call, Ohlc } from "../../charts/series";

export type Verdict = "sell" | "weak" | "buy" | "keep" | "watch";
export type Trade = { date: string; kind: "buy" | "sell"; qty: number };
export type StockView = {
  id: string;
  name: string;
  symbol: string;
  sector: string;
  exchange: "NSE" | "BSE";
  verdict: Verdict;
  /** 0..100 for the Strong / Fair / Weak meter. */
  strength: number;
  trades: Trade[];
  /** Seconds since the price was taken. */
  ageSeconds: number;
};

export type Change = { at: string; from: Verdict; to: Verdict; was: number; now: number };
export type CallCardData = {
  chance: number;
  base: number;
  horizon: string;
  why: string;
  risks: string[];
  ifYouAct: string;
  tax: string;
  buyIf: string;
  sellIf: string;
  couldRise: string;
  track: { n: number; beat: number };
  limited: boolean;
  changed?: Change;
};
export type Fact = {
  id: string;
  value: string;
  sector: string;
  better: "better" | "same" | "worse";
  sentence: string;
  how: string;
};
export type Holding = {
  qty: number;
  avg: number;
  cost: number;
  value: number;
  gain: number;
  gainPct: number;
  share: number;
  longTerm: boolean;
  bought: string;
  ltFrom: string;
  account: "Kite" | "Smallcase";
  tax: string;
};
export type NewsItem = {
  id: string;
  title: string;
  source: string;
  kind: "filing" | "wire" | "blog";
  age: string;
  matters: number;
  line: string;
  hits: { id: string; rel: "direct" | "sector"; dir: "helps" | "hurts" | "none"; size: number }[];
};
export type Reason = "top" | "near" | "view" | "held" | "fall" | "busy";
export type TodayGroup = "sell" | "weak" | "keep" | "near" | "odd";

export const STOCKS: StockView[] = [];
export const UNIVERSE: StockView[] = [];
export const HOLDINGS: { st: StockView; h: Holding }[] = [];
export const NEWS: NewsItem[] = [];
export const UNUSUAL: Record<string, string> = {};
export const GROUP_ORDER: Verdict[] = ["sell", "weak", "buy", "keep", "watch"];

export const stockById = (id: string) => STOCKS.find((s) => s.id === id);
export const universeById = (id: string) => UNIVERSE.find((s) => s.id === id);
export const newsFor = (st: StockView) => NEWS.filter((x) => x.hits.some((h) => h.id === st.id));
export const similar = (_st: StockView): StockView[] => [];
export const isHeld = (st: StockView) => HOLDINGS.some((r) => r.st.id === st.id);
export const holdingOf = (_st: StockView): Holding | null => null;
export const facts = (_st: StockView): Fact[] => [];
export const reasonsOf = (_st: StockView): Reason[] => [];
export const barsOf = (_st: StockView): Ohlc[] => [];
export const history = (_st: StockView): Ohlc[] => [];
/** The forecast band for a stock; empty until the call's own numbers are wired. */
export const callFor = (_last: number, _verdict: Verdict): Call => ({
  low: [0, 0, 0],
  likely: [0, 0, 0],
  high: [0, 0, 0],
});
export const quote = (_st: StockView) => ({ last: 0, day: 0, closes: [] as number[] });
export const peOf = (_st: StockView) => 0;
export const growthOf = (_st: StockView) => 0;
/** The call card a stock row would open with. Nothing is known yet, so every figure is empty. */
export function callCard(_st: StockView): CallCardData {
  return {
    chance: 0,
    base: 0,
    horizon: "",
    why: "",
    risks: [],
    ifYouAct: "",
    tax: "",
    buyIf: "",
    sellIf: "",
    couldRise: "",
    track: { n: 0, beat: 0 },
    limited: true,
  };
}
export function todayGroups() {
  const out: Record<TodayGroup, StockView[]> = { sell: [], weak: [], keep: [], near: [], odd: [] };
  return out;
}
/** One pure function: the day's call line. Today and the email render the same line. */
export function callLine(g: ReturnType<typeof todayGroups>) {
  const first = g.sell[0] ?? g.near[0];
  if (!first) return { kind: "none" as const };
  const after = g.sell[0] ? g.near.find((s) => s.verdict === "buy") : g.near[1];
  return { kind: "act" as const, first, after };
}
