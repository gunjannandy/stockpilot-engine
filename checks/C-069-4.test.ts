// C-069-4: the own record's pairs come from the tax matcher (first in, first out), tagged with the buying route.
// C-062-5: Fidelity statement lots replace the documents' lots up to the statement day; the gap is one estimate.
import { describe, expect, it } from "vitest";
import type { Day } from "../money/src/core/dates";
import { rebuild } from "../money/src/lots/rebuild";
import type { Trade } from "../money/src/lots/types";
import { buildPairs } from "../money/src/record/pairs";
import { buildRecord } from "../money/src/record/record";

const lot = (
  id: number,
  symbol: string,
  on: Day,
  quantity: number,
  cost: number,
  route?: string,
) => ({
  id,
  symbol,
  isin: `IN${symbol}`,
  kind: "stock",
  acquired_on: on,
  quantity,
  cost_per_unit: cost,
  currency: "INR",
  route,
});
const sale = (symbol: string, on: Day, quantity: number, price: number) => ({
  symbol,
  isin: `IN${symbol}`,
  kind: "stock",
  sold_on: on,
  quantity,
  price_per_unit: price,
  currency: "INR",
});

describe("C-069-4 pairs for the own record", () => {
  it("one sale over two lots is two pairs, oldest lot first, with the lot's route", () => {
    const pairs = buildPairs(
      [
        lot(1, "AAA", "2025-01-10", 4, 100, "kite"),
        lot(2, "AAA", "2025-02-10", 6, 110, "smallcase"),
      ],
      [sale("AAA", "2025-06-10", 7, 150)],
    );
    expect(pairs).toEqual([
      {
        route: "kite",
        symbol: "AAA",
        acquiredOn: "2025-01-10",
        soldOn: "2025-06-10",
        quantity: 4,
        cost: 400,
        proceeds: 600,
        gain: 200,
      },
      {
        route: "smallcase",
        symbol: "AAA",
        acquiredOn: "2025-02-10",
        soldOn: "2025-06-10",
        quantity: 3,
        cost: 330,
        proceeds: 450,
        gain: 120,
      },
    ]);
  });

  it("a lot with no route takes its stock's first route, else the father's own", () => {
    const pairs = buildPairs(
      [
        lot(1, "AAA", "2025-01-10", 1, 100, "smallcase"),
        lot(2, "AAA", "2025-02-10", 1, 0), // a bonus
        lot(3, "BBB", "2025-01-10", 1, 50), // untagged, no sibling
      ],
      [sale("AAA", "2025-06-10", 2, 100), sale("BBB", "2025-06-10", 1, 60)],
    );
    expect(pairs.map((p) => [p.symbol, p.route])).toEqual([
      ["AAA", "smallcase"],
      ["AAA", "smallcase"],
      ["BBB", "kite"],
    ]);
  });

  it("funds, RSUs and dollar lots never pair", () => {
    const pairs = buildPairs(
      [
        { ...lot(1, "FUND", "2025-01-10", 1, 10), kind: "mf" },
        { ...lot(2, "NOW", "2025-01-10", 1, 10), kind: "rsu", currency: "USD" },
        lot(3, "AAA", "2025-01-10", 1, 10, "kite"),
      ],
      [{ ...sale("FUND", "2025-06-10", 1, 12), kind: "mf" }, sale("AAA", "2025-06-10", 1, 12)],
    );
    expect(pairs.map((p) => p.symbol)).toEqual(["AAA"]);
  });

  it("feeds the record: smallcase pairs stay out, the father's sale counts once", () => {
    const pairs = buildPairs(
      [
        lot(1, "AAA", "2025-01-10", 4, 100, "kite"),
        lot(2, "AAA", "2025-02-10", 6, 110, "kite"),
        lot(3, "BBB", "2025-01-10", 5, 10, "smallcase"),
      ],
      [sale("AAA", "2025-06-10", 7, 150), sale("BBB", "2025-06-10", 5, 20)],
    );
    const r = buildRecord({
      pairs,
      asOf: "2025-12-31",
      prices: {},
      nifty: { on: () => null, near: () => null } as never,
    });
    expect(r.closed).toBe(1);
    expect(r.winners).toBe(1);
  });
});

describe("C-062-5 Fidelity lots in the rebuild", () => {
  const ISIN = "US0000000001";
  const rateOn = () => 80;
  const vest = (key: string, day: Day, qty: number, price: number): Trade => ({
    source: "fidelity_docs",
    sourceRef: key,
    kind: "rsu",
    symbol: "NOW",
    isin: ISIN,
    side: "vest",
    tradeDate: day,
    quantity: qty,
    price,
    currency: "USD",
    tradeKey: key,
  });
  const docs = [
    vest("a", "2024-08-16", 12, 100),
    vest("b", "2025-11-14", 6, 90),
    vest("c", "2026-02-09", 3, 70),
  ];
  const statement = [
    {
      asOf: "2025-12-31",
      symbol: "NOW",
      isin: ISIN,
      acquiredOn: "2024-08-17",
      quantity: 10,
      costBasisInr: 100000,
    },
    {
      asOf: "2025-12-31",
      symbol: "NOW",
      isin: ISIN,
      acquiredOn: "2025-11-17",
      quantity: 5.5,
      costBasisInr: 50000,
    },
  ];
  const holdings = [
    { asOf: "2026-11-24", symbol: "NOW", isin: ISIN, quantity: 20, costBasisInr: 200000 },
  ];

  it("statement lots replace the documents up to its day; later vests stay; the rest is one estimate", () => {
    const { lots } = rebuild({
      trades: docs,
      actions: [],
      fidelityLots: statement,
      fidelityHoldings: holdings,
      rateOn,
    });
    expect(lots.map((l) => [l.acquiredOn, l.quantity, l.source, l.estimated])).toEqual([
      ["2026-02-09", 3, "trades:fidelity_docs", false],
      ["2024-08-17", 10, "trades:fidelity_statement", false],
      ["2025-11-17", 5.5, "trades:fidelity_statement", false],
      ["2026-11-24", 1.5, "trades:estimated", true],
    ]);
    const stmt = lots[1];
    expect((stmt?.costPerUnit ?? 0) * 10 * 80).toBeCloseTo(100000, 3); // Fidelity's rupee cost, not a rate guess
    // the estimate is priced so the whole holding costs 200000: (200000 - 100000 - 50000 - 3*70*80) / 1.5 / 80
    expect(lots[3]?.costPerUnit).toBeCloseTo(33200 / 1.5 / 80, 5);
  });

  it("a sale after the statement day closes the statement's lots first in, first out", () => {
    const sell: Trade = { ...vest("s", "2026-03-01", 12, 0), side: "sell", sourceRef: "s" };
    const { lots } = rebuild({
      trades: [...docs, sell],
      actions: [],
      fidelityLots: statement,
      rateOn,
    });
    const stmt = lots.filter((l) => l.source === "trades:fidelity_statement");
    expect(stmt.map((l) => l.closedQuantity)).toEqual([10, 2]);
  });

  it("no statement and no holding leaves the documents' lots alone", () => {
    const { lots } = rebuild({ trades: docs, actions: [], rateOn });
    expect(lots).toHaveLength(3);
  });

  it("a holding with no rate, no gap or no cost basis adds nothing", () => {
    const h0 = holdings[0] as (typeof holdings)[number];
    const run = (h: typeof holdings, r: typeof rateOn | null = rateOn) =>
      rebuild({ trades: docs, actions: [], fidelityHoldings: h, rateOn: r }).lots.length;
    expect(run(holdings, null)).toBe(3);
    expect(run([{ ...h0, quantity: 22 }], () => null)).toBe(3);
    expect(run([{ ...h0, quantity: 22 }])).toBe(4);
    expect(run([{ ...h0, quantity: 22, costBasisInr: null as never }])).toBe(3);
    expect(run([{ ...h0, quantity: 22, costBasisInr: 1 }])).toBe(3); // the documents already cost more
  });
});
