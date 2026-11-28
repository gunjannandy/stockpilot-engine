import type { Day } from "../core/dates";

/** One executed trade (or a vest), as every source writes it. Dates are plain `YYYY-MM-DD`. */
export type Trade = {
  source: string; // tradebook | contract_note | coin | cas | fidelity | rsu_inference
  sourceRef: string;
  kind: string; // stock | mf | rsu
  symbol: string;
  isin: string | null;
  side: string; // buy | sell | vest | credit | debit
  tradeDate: Day;
  quantity: number;
  price: number | null;
  currency?: string; // default INR
  status?: string; // default confirmed; "expected" vests never become lots
  tradeKey?: string | null;
};

/** A split, bonus, demerger or rights issue. */
export type Action = {
  symbol: string;
  isin: string | null;
  exDate: Day;
  kind: string; // split | bonus | demerger | rights
  numerator: number;
  denominator: number;
  newIsin?: string | null;
  newSymbol?: string | null;
  costFraction?: number | null;
  price?: number | null;
  source?: string | null; // nse | yfinance | owner; absent means nse
};

/** What Kite showed at its latest sync; the caller passes only the latest snapshot's rows. */
export type KiteRow = {
  kind: string;
  symbol: string;
  isin: string | null;
  quantity: number;
  avgPrice: number;
};
export type KiteSnapshot = { at: Day; rows: KiteRow[] };

export type Lot = {
  kind: string;
  symbol: string;
  isin: string | null;
  on: Day;
  qty: number;
  cost: number;
  closed: number;
  cur: string;
  src: string;
  ref: string;
  estimated?: boolean;
};

export type Sale = {
  kind: string;
  symbol: string;
  isin: string | null;
  soldOn: Day;
  quantity: number;
  pricePerUnit: number;
  currency: string;
  source: string;
  sourceRef: string;
};

/** A lot as the lots table stores it (rounded to 6 places, source marked `trades:`). */
export type StoredLot = {
  kind: string;
  symbol: string;
  isin: string | null;
  acquiredOn: Day;
  quantity: number;
  costPerUnit: number;
  currency: string;
  closedQuantity: number;
  source: string;
  sourceRef: string;
  estimated: boolean;
};

/** USD/INR on or before a day; null or absent when there is none. */
export type RateOn = ((day: Day) => number | null | undefined) | null | undefined;

/** One row of Fidelity's "Current Shares" export: a lot as it stood on `asOf`, its cost in rupees. */
export type FidelityStatementLot = {
  asOf: Day;
  symbol: string;
  isin: string | null;
  acquiredOn: Day;
  quantity: number;
  costBasisInr: number;
};

/** One row of Fidelity's Stock Plan statement: shares held on `asOf` and what they cost in rupees. */
export type FidelityHolding = {
  asOf: Day;
  symbol: string;
  isin: string | null;
  quantity: number;
  costBasisInr: number | null;
};

export type RebuildInput = {
  trades: Trade[]; // in the order they were saved: ties on a date keep it
  actions: Action[];
  /** symbol -> ISIN as the exchange lists it today (the `stocks` table). */
  stocks?: Record<string, string>;
  kite?: KiteSnapshot | null;
  /** Fidelity's statement lots and holdings (all stored rows) and the dollar rate; absent means no Fidelity data. */
  fidelityLots?: FidelityStatementLot[];
  fidelityHoldings?: FidelityHolding[];
  rateOn?: RateOn;
};

export type RebuildResult = {
  lots: StoredLot[];
  sales: Sale[];
  /** [isin or symbol, day, quantity left over] for sells no lot could cover. */
  unmatchedSells: [string, Day, number][];
};

export type Holding = {
  kind: string;
  symbol: string;
  isin: string | null;
  quantity: number;
  avgCost: number;
  currency: string;
};
