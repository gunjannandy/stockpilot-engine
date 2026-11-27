// Concentration and the Nifty −10% shock. Pure arithmetic on priced positions.
export type Exposure = {
  symbol: string;
  sector: string | null;
  value: number;
  beta: number | null;
};

export type Slice = { key: string; value: number; share: number };

function slices(values: Map<string, number>, total: number): Slice[] {
  return [...values.entries()]
    .map(([key, value]) => ({ key, value, share: total ? value / total : 0 }))
    .sort((a, b) => b.value - a.value || (a.key < b.key ? -1 : 1));
}

export type Concentration = {
  total: number;
  byStock: Slice[];
  bySector: Slice[];
  /** Stocks or sectors above their limit, largest first; the caller words them. */
  flags: { kind: "stock" | "sector"; key: string; share: number }[];
};

export const STOCK_LIMIT = 0.15;
export const SECTOR_LIMIT = 0.3;

export function concentration(
  items: readonly Exposure[],
  limits: { stock: number; sector: number } = { stock: STOCK_LIMIT, sector: SECTOR_LIMIT },
): Concentration {
  const stock = new Map<string, number>();
  const sector = new Map<string, number>();
  let total = 0;
  for (const i of items) {
    if (!(i.value > 0)) continue;
    total += i.value;
    stock.set(i.symbol, (stock.get(i.symbol) ?? 0) + i.value);
    const s = i.sector || "Unknown";
    sector.set(s, (sector.get(s) ?? 0) + i.value);
  }
  const byStock = slices(stock, total);
  const bySector = slices(sector, total);
  const flags = [
    ...byStock
      .filter((s) => s.share > limits.stock)
      .map((s) => ({ kind: "stock" as const, key: s.key, share: s.share })),
    ...bySector
      .filter((s) => s.share > limits.sector && s.key !== "Unknown")
      .map((s) => ({ kind: "sector" as const, key: s.key, share: s.share })),
  ].sort((a, b) => b.share - a.share);
  return { total, byStock, bySector, flags };
}

export type Shock = {
  fall: number; // the Nifty move, e.g. -0.1
  total: number;
  lossInr: number; // negative when the book falls
  lossShare: number;
  perStock: { symbol: string; move: number; changeInr: number }[];
  assumedBeta: string[]; // symbols with no beta, taken as 1
};

/** If the Nifty moves `fall` (default −10%), each holding moves beta × fall. No beta counts as 1. */
export function niftyShock(items: readonly Exposure[], fall = -0.1): Shock {
  let total = 0;
  let change = 0;
  const assumedBeta: string[] = [];
  const perStock = items
    .filter((i) => i.value > 0)
    .map((i) => {
      const beta = i.beta ?? 1;
      if (i.beta === null) assumedBeta.push(i.symbol);
      const move = beta * fall;
      const changeInr = i.value * move;
      total += i.value;
      change += changeInr;
      return { symbol: i.symbol, move, changeInr };
    })
    .sort((a, b) => a.changeInr - b.changeInr);
  return {
    fall,
    total,
    lossInr: change,
    lossShare: total ? change / total : 0,
    perStock,
    assumedBeta,
  };
}
