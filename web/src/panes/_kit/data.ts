// Made-up prototype data shared by every v3 screen. Invented names, seeded numbers; nothing real.
import { history, type SampleStock, STOCKS, type Verdict } from "../stock/sample";

export { STOCKS, type SampleStock, type Verdict };

const cache = new Map<string, { last: number; day: number; closes: number[] }>();
export function quote(st: SampleStock) {
  let q = cache.get(st.id);
  if (!q) {
    const h = history(st);
    const closes = h.map((b) => b.close);
    const last = closes[closes.length - 1] ?? 0;
    const prev = closes[closes.length - 2] ?? last;
    q = { last, day: (last / prev - 1) * 100, closes: closes.slice(-130) };
    cache.set(st.id, q);
  }
  return q;
}

export const RS = "₹";
export const money = (v: number, dp = v < 1000 ? 1 : 0) =>
  `${v < 0 ? "−" : ""}${RS}${Math.abs(v).toLocaleString("en-IN", { maximumFractionDigits: dp })}`;
export const lakh = (v: number) =>
  Math.abs(v) >= 1e7
    ? `${RS}${(v / 1e7).toFixed(2)} crore`
    : Math.abs(v) >= 1e5
      ? `${RS}${(v / 1e5).toFixed(2)} lakh`
      : money(v);
export const pct = (v: number, dp = 1) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(dp)}%`;

const pick = <T>(a: T[], seed: number) => a[Math.abs(seed) % a.length] as T;
const n = (st: SampleStock, k: number, lo: number, hi: number) => {
  const x = Math.abs(Math.sin(st.seed * 12.9898 + k * 78.233) * 43758.5453) % 1;
  return lo + x * (hi - lo);
};

export type Fact = {
  id: string;
  value: string;
  sector: string;
  better: "better" | "same" | "worse";
  sentence: string;
  how: string;
};
/** Seven facts in plain words, each against the sector. */
export function facts(st: SampleStock): Fact[] {
  const pe = n(st, 1, 9, 42);
  const spe = n(st, 2, 14, 30);
  const roe = n(st, 3, 6, 26);
  const sroe = n(st, 4, 10, 18);
  const debt = n(st, 5, 0, 1.8);
  const sdebt = n(st, 6, 0.3, 1);
  const gro = n(st, 7, -8, 28);
  const sgro = n(st, 8, 4, 14);
  const swing = n(st, 9, 12, 38);
  const fall = n(st, 10, 18, 61);
  const vol = n(st, 11, 0.5, 3.2);
  const cmp = (a: number, b: number, lowerIsBetter = false): Fact["better"] =>
    Math.abs(a - b) / (Math.abs(b) || 1) < 0.08
      ? "same"
      : a < b === lowerIsBetter
        ? "better"
        : "worse";
  return [
    {
      id: "pe",
      value: `${RS}${pe.toFixed(0)}`,
      sector: `${RS}${spe.toFixed(0)}`,
      better: cmp(pe, spe, true),
      sentence: `You pay ${RS}${pe.toFixed(0)} for every ${RS}1 of yearly profit. Companies like it cost ${RS}${spe.toFixed(0)}.`,
      how: "Price today divided by the last four quarters of profit per share. Sector figure is the middle company in the same sector.",
    },
    {
      id: "roe",
      value: `${roe.toFixed(0)}%`,
      sector: `${sroe.toFixed(0)}%`,
      better: cmp(roe, sroe),
      sentence: `For every ${RS}100 the owners put in, it earns ${RS}${roe.toFixed(0)} a year. The sector earns ${RS}${sroe.toFixed(0)}.`,
      how: "Yearly profit divided by the owners' money in the business (return on equity), from the latest annual filing.",
    },
    {
      id: "debt",
      value: `${debt.toFixed(1)}×`,
      sector: `${sdebt.toFixed(1)}×`,
      better: cmp(debt, sdebt, true),
      sentence: `It owes ${debt.toFixed(1)} times what the owners put in. Companies like it owe ${sdebt.toFixed(1)} times.`,
      how: "Total borrowings divided by the owners' money, from the latest balance sheet.",
    },
    {
      id: "growth",
      value: pct(gro, 0),
      sector: pct(sgro, 0),
      better: cmp(gro, sgro),
      sentence: `Profit ${gro >= 0 ? "grew" : "fell"} ${Math.abs(gro).toFixed(0)}% over the last year. The sector grew ${sgro.toFixed(0)}%.`,
      how: "Profit of the last four quarters against the four before them.",
    },
    {
      id: "swing",
      value: `${swing.toFixed(0)}%`,
      sector: `${(swing * 0.8).toFixed(0)}%`,
      better: cmp(swing, swing * 0.8, true),
      sentence: `In a usual year the price swings about ${swing.toFixed(0)}% up or down.`,
      how: "Yearly volatility: how far the price usually moves from its yearly average, from daily closes.",
    },
    {
      id: "fall",
      value: `−${fall.toFixed(0)}%`,
      sector: `−${(fall * 0.9).toFixed(0)}%`,
      better: cmp(fall, fall * 0.9, true),
      sentence: `Its worst fall from a high was ${fall.toFixed(0)}%. If that happened again, ${RS}100 would drop to ${RS}${(100 - fall).toFixed(0)}.`,
      how: "The biggest drop from a peak to the next low since listing.",
    },
    {
      id: "trading",
      value: `${vol.toFixed(1)} lakh`,
      sector: `${(vol * 1.1).toFixed(1)} lakh`,
      better: cmp(vol, vol * 1.1),
      sentence: `About ${vol.toFixed(1)} lakh shares change hands on a normal day, so you can sell without moving the price.`,
      how: "Average shares traded per day over the last three months.",
    },
  ];
}

const WHY: Record<Verdict, string[]> = {
  sell: [
    "The price has broken its recent floor and the company's own news is poor.",
    "Profit margins are shrinking and the chance of beating the Nifty fell this month.",
  ],
  weak: ["Growth is slowing against the sector. Do not add money now."],
  buy: ["Earnings beat and the price sits close to its 50-day average, a fair place to buy."],
  keep: ["Fairly priced with no change in the view. Nothing to do today."],
  watch: [
    "Strong profit growth and the price is near its 50-day average. Worth watching for a dip.",
  ],
};
const RISK = [
  "A weak monsoon would cut demand.",
  "Debt rose over the last two quarters.",
  "One large customer is a quarter of sales.",
  "The next results may disappoint.",
];
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
  /** A change since the last look, as numbers: the call and the chance before and after. */
  changed?: Change;
};
export type Change = { at: string; from: Verdict; to: Verdict; was: number; now: number };
const CHANGES: Record<string, Change> = {
  "alpha-steel": { at: "09:42", from: "keep", to: "sell", was: 44, now: 34 },
  "echo-bank": { at: "08:15", from: "buy", to: "buy", was: 67, now: 74 },
};
export function callCard(st: SampleStock): CallCardData {
  const last = quote(st).last;
  const strength = st.strength;
  const chance = CHANGES[st.id]?.now ?? Math.round(30 + strength * 0.5);
  const k = st.verdict === "sell" ? 0.9 : st.verdict === "buy" ? 1.12 : 1.05;
  const held = st.trades.reduce((q, t) => q + (t.kind === "buy" ? t.qty : -t.qty), 0);
  return {
    chance,
    base: Math.round(40 + n(st, 20, 0, 80)),
    horizon: "6 months",
    why: pick(WHY[st.verdict], st.seed),
    risks: [pick(RISK, st.seed), pick(RISK, st.seed + 1)].filter((x, i, a) => a.indexOf(x) === i),
    ifYouAct:
      held > 0
        ? st.verdict === "sell"
          ? `Selling all ${held} shares now would bring in ${money(held * last, 0)}.`
          : `We hold ${held} shares worth ${money(held * last, 0)}. No action needed.`
        : `We hold none. ${st.verdict === "buy" ? `A first buy of ${money(last * 10, 0)} would be about 10 shares.` : "No action needed."}`,
    tax:
      held > 0
        ? st.verdict === "sell"
          ? "Selling now books a long-term gain. It falls inside this year's tax-free room."
          : "No tax unless we sell."
        : "No tax: we do not hold it.",
    buyIf: `${money(last * 0.93, 0)}, about 7% lower`,
    sellIf: `${money(last * 0.91, 0)}, about 9% lower`,
    couldRise: `${money(last * k, 0)} in 6 months`,
    track: { n: 24, beat: Math.round(8 + strength / 8) },
    limited: st.seed % 7 === 0,
    changed: CHANGES[st.id],
  };
}

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
export function holdingOf(st: SampleStock): Holding | null {
  const qty = st.trades.reduce((q, t) => q + (t.kind === "buy" ? t.qty : -t.qty), 0);
  if (qty <= 0) return null;
  const last = quote(st).last;
  const first = st.trades.find((t) => t.kind === "buy");
  const avg = last * (0.78 + n(st, 30, 0, 0.35));
  const bought = first?.date ?? "2025-04-10";
  const lt = new Date(`${bought}T00:00:00Z`);
  lt.setUTCFullYear(lt.getUTCFullYear() + 1);
  const ltFrom = lt.toISOString().slice(0, 10);
  const cost = avg * qty;
  const value = last * qty;
  return {
    qty,
    avg,
    cost,
    value,
    gain: value - cost,
    gainPct: (value / cost - 1) * 100,
    share: 0,
    longTerm: ltFrom <= "2026-11-27",
    bought,
    ltFrom,
    account: st.seed % 3 === 0 ? "Smallcase" : "Kite",
    tax:
      ltFrom <= "2026-11-27"
        ? "Long term: taxed at the lower rate above the tax-free room"
        : `Short term until ${ltFrom}`,
  };
}
export const HOLDINGS = (() => {
  const rows = STOCKS.map((s) => ({ st: s, h: holdingOf(s) })).filter(
    (r): r is { st: SampleStock; h: Holding } => r.h !== null,
  );
  const total = rows.reduce((a, r) => a + r.h.value, 0);
  for (const r of rows) r.h.share = (r.h.value / total) * 100;
  return rows;
})();

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
export const NEWS: NewsItem[] = [
  {
    id: "n1",
    title: "Cement makers cut prices as monsoon demand stays weak",
    source: "Dalal Daily",
    kind: "wire",
    age: "42 min ago",
    matters: 92,
    line: "Bad for cement. The stock with the least room to absorb it is hit hardest.",
    hits: [
      { id: "alpha-steel", rel: "direct", dir: "hurts", size: 3 },
      { id: "indigo-cement", rel: "direct", dir: "hurts", size: 2 },
      { id: "nova-realty", rel: "sector", dir: "none", size: 0 },
    ],
  },
  {
    id: "n2",
    title: "Steel imports fall to a 2-year low after new duty",
    source: "Market Ledger",
    kind: "wire",
    age: "2h ago",
    matters: 88,
    line: "Good for domestic steel makers. Helps margins.",
    hits: [
      { id: "alpha-steel", rel: "direct", dir: "helps", size: 2 },
      { id: "bravo-motors", rel: "sector", dir: "none", size: 0 },
    ],
  },
  {
    id: "n3",
    title: "Echo Bank files strong quarterly results",
    source: "Exchange filing",
    kind: "filing",
    age: "3h ago",
    matters: 85,
    line: "Profit beat estimates. The bank raised its payout.",
    hits: [{ id: "echo-bank", rel: "direct", dir: "helps", size: 3 }],
  },
  {
    id: "n4",
    title: "Telecom tariffs may rise next quarter, analysts say",
    source: "Street Notes",
    kind: "blog",
    age: "5h ago",
    matters: 41,
    line: "A guess, not a fact. Treat with care.",
    hits: [{ id: "lima-telecom", rel: "direct", dir: "helps", size: 1 }],
  },
];
export const stockById = (id: string) => STOCKS.find((s) => s.id === id);
export const newsFor = (st: SampleStock) => NEWS.filter((x) => x.hits.some((h) => h.id === st.id));

export const similar = (st: SampleStock) =>
  STOCKS.filter((s) => s.id !== st.id)
    .sort((a, b) => Math.abs(a.strength - st.strength) - Math.abs(b.strength - st.strength))
    .slice(0, 3);

export const GROUP_ORDER: Verdict[] = ["sell", "weak", "buy", "keep", "watch"];

export const UNUSUAL: Record<string, string> = {
  "kilo-retail": "Traded four times its usual volume today.",
  "lima-telecom": "Jumped 5% after a tariff rumour.",
};
export const isHeld = (st: SampleStock) => HOLDINGS.some((r) => r.st.id === st.id);
export type TodayGroup = "sell" | "weak" | "keep" | "near" | "odd";
export function todayGroups() {
  const out: Record<TodayGroup, SampleStock[]> = {
    sell: [],
    weak: [],
    keep: [],
    near: [],
    odd: [],
  };
  for (const s of STOCKS) {
    if (UNUSUAL[s.id]) out.odd.push(s);
    else if (s.verdict === "sell") out.sell.push(s);
    else if (s.verdict === "weak") out.weak.push(s);
    else if (s.verdict === "keep") out.keep.push(s);
    else out.near.push(s);
  }
  return out;
}
/** One pure function: the day's call line. Today and the email render the same line. */
export function callLine(g: ReturnType<typeof todayGroups>) {
  const first = g.sell[0] ?? g.near[0];
  if (!first) return { kind: "none" as const };
  const after = g.sell[0] ? g.near.find((s) => s.verdict === "buy") : g.near[1];
  return { kind: "act" as const, first, after };
}
const barsCache = new Map<string, ReturnType<typeof history>>();
export const barsOf = (st: SampleStock) => {
  let b = barsCache.get(st.id);
  if (!b) {
    b = history(st);
    barsCache.set(st.id, b);
  }
  return b;
};

const ADJ = [
  "Blue",
  "Cedar",
  "Delta",
  "Ember",
  "Falcon",
  "Granite",
  "Harbor",
  "Indus",
  "Jade",
  "Kestrel",
  "Lotus",
  "Maple",
  "Nimbus",
  "Orbit",
  "Pine",
  "Quartz",
  "Raven",
  "Sable",
  "Teak",
  "Umber",
  "Vertex",
  "Willow",
  "Xenon",
  "Yarrow",
  "Zephyr",
  "Amber",
];
const KIND: [string, string][] = [
  ["Foods", "Consumer"],
  ["Cables", "Industrials"],
  ["Pharma", "Health"],
  ["Housing", "Finance"],
  ["Textiles", "Textiles"],
  ["Logistics", "Transport"],
  ["Agro", "Agri"],
  ["Software", "IT"],
  ["Paints", "Materials"],
  ["Hotels", "Leisure"],
];
/** Every stock in the made-up universe: the 14 named ones plus generated fillers, so the screener has something to sift. */
export const UNIVERSE: SampleStock[] = [
  ...STOCKS,
  ...Array.from({ length: 30 }, (_, i): SampleStock => {
    const [kind, sector] = KIND[i % KIND.length] as [string, string];
    const name = `${ADJ[i % ADJ.length]} ${kind}`;
    const v: Verdict = i % 5 === 0 ? "buy" : i % 3 === 0 ? "weak" : i % 7 === 0 ? "sell" : "watch";
    return {
      id: name.toLowerCase().replace(/\W+/g, "-"),
      name,
      symbol: name.toUpperCase().replace(/\W+/g, "").slice(0, 9),
      sector,
      exchange: i % 4 === 0 ? "BSE" : "NSE",
      verdict: v,
      strength: 22 + ((i * 17) % 60),
      seed: 30 + i,
      start: 150 + ((i * 97) % 2400),
      drift: ((i % 5) - 2) * 0.0002,
      trades: [],
      ageSeconds: 30,
    };
  }),
];
export const universeById = (id: string) => UNIVERSE.find((s) => s.id === id);

export type Reason = "top" | "near" | "view" | "held" | "fall" | "busy";
export function reasonsOf(st: SampleStock): Reason[] {
  const r: Reason[] = [];
  const k = UNIVERSE.indexOf(st);
  if (k % 4 === 0) r.push("top");
  else if (k % 4 === 1) r.push("near");
  if (st.verdict !== "watch" || st.seed % 2) r.push("view");
  if (isHeld(st)) r.push("held");
  if (st.drift < 0 || st.seed % 6 === 0) r.push("fall");
  if (UNUSUAL[st.id] || st.seed % 5 === 0) r.push("busy");
  return r;
}

export const peOf = (s: SampleStock) => 8 + ((s.seed * 7) % 30);
export const growthOf = (s: SampleStock) => ((s.seed * 11) % 40) - 8;
