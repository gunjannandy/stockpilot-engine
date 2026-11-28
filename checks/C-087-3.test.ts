// C-087-1 and C-088-1 on the Worker side: scores are insert-only, and the track record and adding value are read from them.
import { expect, it } from "vitest";
import { makeApp } from "../api/src/testkit";
import { callBase } from "./calls-fixture";

it("scores are written once, and the record reads Brier, hit rate and adding value from them", async () => {
  const t = await makeApp();
  const rows = Array.from({ length: 4 }, (_, i) =>
    callBase({
      id: `NSE:S${i}:2026-06-01:63`,
      symbol: `S${i}`,
      made_on: "2026-06-01",
      chance: 0.6,
      base_rate: 0.5,
    }),
  );
  await t.signed("POST", "/api/calls/publish", { rows });
  const score = (i: number, beat: boolean) => ({
    call_id: `NSE:S${i}:2026-06-01:63`,
    beat,
    scored_on: "2026-11-28",
    stock_ret: beat ? 0.2 : -0.1,
    nifty_ret: 0.05,
    equal_ret: 0.08,
  });
  const body = { scores: [score(0, true), score(1, true), score(2, true), score(3, false)] };
  expect(
    ((await (await t.signed("POST", "/api/record/scores", body)).json()) as { written: number })
      .written,
  ).toBe(4);
  const again = (await (
    await t.signed("POST", "/api/record/scores", { scores: [score(0, false)] })
  ).json()) as {
    written: number;
  };
  expect(again.written).toBe(0);
  const r = (await (await t.app.request("/api/record")).json()) as {
    lines: {
      horizon_days: number;
      n: number;
      buy_hit_rate: number;
      brier: number;
      base_brier: number;
      verdict: string;
    }[];
    value: { n: number; ours_pct: number; nifty_pct: number; adding: boolean | null };
  };
  const l = r.lines.find((x) => x.horizon_days === 63);
  expect(l?.n).toBe(4);
  expect(l?.buy_hit_rate).toBeCloseTo(0.75);
  expect(l?.brier).toBeCloseTo((3 * 0.16 + 0.36) / 4);
  expect(l?.base_brier).toBeCloseTo(0.25);
  expect(l?.verdict).toBe("too early");
  expect(r.value.n).toBe(4);
  expect(r.value.nifty_pct).toBe(5);
  expect(r.value.adding).toBeNull();
});

it("tells the Job which ended calls have no score yet", async () => {
  const t = await makeApp({ now: () => new Date("2026-11-28T06:00:00Z") });
  await t.signed("POST", "/api/calls/publish", {
    rows: [
      callBase({ id: "NSE:OLD:2026-06-01:63", symbol: "OLD", made_on: "2026-06-01" }),
      callBase({ id: "NSE:NEW:2026-11-01:63", symbol: "NEW", made_on: "2026-11-01" }),
    ],
  });
  const r = (await (await t.signed("GET", "/api/record/inputs")).json()) as {
    calls: { id: string }[];
  };
  expect(r.calls.map((c) => c.id)).toEqual(["NSE:OLD:2026-06-01:63"]);
});
