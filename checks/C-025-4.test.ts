// C-025-4: the call line is one money function; Today and the email render the same line from fixtures.
import { readFileSync, readdirSync } from "node:fs";
import { expect, it } from "vitest";
import { makeApp } from "../api/src/testkit";
import { callLine } from "../money/src/callline/callline";
import { callBase } from "./calls-fixture";

const call = (symbol: string, verdict: string, chance: number | null) => ({
  symbol,
  verdict,
  chance,
  madeOn: "2026-11-28",
});
const none = new Set<string>();

it("C-025-4 sell on a holding first, then the best buy with money left, else nothing", () => {
  const calls = [
    call("AAA", "Sell", 0.2),
    call("BBB", "Buy", 0.7),
    call("CCC", "Buy", 0.6),
    call("DDD", "Sell", 0.1),
  ];
  const held = new Set(["AAA", "DDD"]);
  expect(callLine({ calls, held, moneyLeft: 1000 })).toMatchObject({
    kind: "sell",
    symbols: ["DDD", "AAA"],
  });
  expect(callLine({ calls, held, moneyLeft: 1000 }).en).toBe("Sell DDD and 1 more today.");
  expect(callLine({ calls: calls.slice(1, 3), held: none, moneyLeft: 1000 }).en).toBe(
    "Consider buying BBB and 1 more: a 70 in 100 chance of beating the Nifty.",
  );
  expect(callLine({ calls: calls.slice(1, 3), held: none, moneyLeft: 0 }).kind).toBe("nothing"); // no money left
  expect(callLine({ calls: [call("AAA", "Sell", 0.2)], held: none, moneyLeft: 5 }).kind).toBe(
    "nothing",
  ); // not held
  expect(
    callLine({
      calls: [call("BBB", "Buy", 0.7)],
      held: none,
      moneyLeft: 5,
      notNow: new Set(["BBB"]),
    }).kind,
  ).toBe("nothing");
  const nothing = callLine({ calls: [], held: none, moneyLeft: null });
  expect(nothing).toMatchObject({ en: "Nothing to do today.", kind: "nothing" });
  expect(nothing.bn).toMatch(/[ঀ-৿]/);
});

it("C-025-4 /api/today carries the same line, and no other code makes one", async () => {
  const t = await makeApp({ now: () => new Date("2026-11-28T06:00:00Z") });
  await t.signed("POST", "/api/calls/publish", {
    rows: [callBase({ id: "NSE:BBB:2026-11-28:63", symbol: "BBB", chance: 0.7 })],
  });
  const r = (await (await t.app.request("/api/today")).json()) as {
    call_line: { en: string; kind: string };
    groups: Record<string, string[]>;
  };
  expect(r.call_line).toEqual({
    ...callLine({ calls: [call("BBB", "Buy", 0.7)], held: none, moneyLeft: null }),
  });
  expect(r.groups.sell).toEqual([]);
  for (const dir of ["today", "email"])
    for (const f of readdirSync(new URL(`../api/src/${dir}/`, import.meta.url)).filter((n) =>
      n.endsWith(".ts"),
    ))
      expect(
        readFileSync(new URL(`../api/src/${dir}/${f}`, import.meta.url), "utf8"),
        f,
      ).not.toMatch(/Nothing to do today/);
});
