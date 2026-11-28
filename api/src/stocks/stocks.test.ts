import { type UniverseRow, unexplainedMove } from "@stockpilot/contract";
import { expect, it } from "vitest";
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
