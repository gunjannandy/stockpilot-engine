import { type UniverseRow, unexplainedMove } from "@stockpilot/contract";
import { expect, it } from "vitest";
import { buildChart } from "./chart";
import { searchUniverse } from "./stocks";

const u = (
  symbol: string,
  name: string,
  status: "listed" | "delisted" = "listed",
): UniverseRow => ({
  id: `NSE:${symbol}`,
  symbol,
  exchange: "NSE",
  segment: "NSE",
  name,
  isin: "",
  aliases: [name.toLowerCase(), symbol.toLowerCase()].join("|"),
  status,
});

it("search finds by symbol and name, exact first, delisted last", () => {
  const rows = [
    u("TATASTEEL", "Tata Steel"),
    u("TATA", "Tata Old", "delisted"),
    u("TATAMOTORS", "Tata Motors"),
  ];
  expect(searchUniverse(rows, "tata").map((r) => r.symbol)).toEqual([
    "TATAMOTORS",
    "TATASTEEL",
    "TATA",
  ]);
  expect(searchUniverse(rows, "TATA")[0]?.symbol).toBe("TATAMOTORS");
  expect(searchUniverse(rows, "motors").map((r) => r.symbol)).toEqual(["TATAMOTORS"]);
  expect(searchUniverse(rows, " ")).toEqual([]);
});

it("a move over 40% with no corporate action is flagged; an explained one is not", () => {
  const rows = [
    { date: "2026-01-01", close: 100 },
    { date: "2026-01-02", close: 101 },
    { date: "2026-01-03", close: 50 },
  ];
  expect(unexplainedMove(rows)).toEqual({ date: "2026-01-03", from: 101, to: 50 });
  expect(unexplainedMove(rows, new Set(["2026-01-03"]))).toBeNull();
  expect(unexplainedMove(rows.slice(0, 2))).toBeNull();
});

it("the chart has no cliff on a split day and ends on the real price, with both averages", () => {
  const rows = Array.from({ length: 250 }, (_, i) => {
    const split = i >= 100;
    const close = split ? 50 + i * 0.01 : 100 + i * 0.02;
    const prev =
      i === 0
        ? null
        : i === 100
          ? 100 + 99 * 0.02
          : i < 100
            ? 100 + (i - 1) * 0.02
            : 50 + (i - 1) * 0.01;
    const d = new Date(Date.UTC(2025, 0, 1) + i * 86400000).toISOString().slice(0, 10);
    return {
      date: d,
      open: close,
      high: close,
      low: close,
      close,
      prev_close: prev && i === 100 ? prev * 0.5 : prev,
      volume: 10,
    };
  });
  const ch = buildChart("AAA", rows);
  expect(ch.c.at(-1)).toBe(rows.at(-1)?.close);
  expect(Math.abs((ch.c[100] ?? 0) / (ch.c[99] ?? 1) - 1)).toBeLessThan(0.01);
  expect(ch.ma2[40]).toBeNull();
  expect(ch.ma2[41]).not.toBeNull();
  expect(ch.ma10[208]).toBeNull();
  expect(ch.ma10[209]).not.toBeNull();
  expect(ch.v[0]).toBe(10);
});
