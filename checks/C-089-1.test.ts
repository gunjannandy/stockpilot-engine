// C-089-1: a missed call at its 3-month score gets exactly one post-mortem row (English and Bengali).
import { expect, it } from "vitest";
import { makeApp } from "../api/src/testkit";

const NOW = new Date("2026-11-28T06:00:00Z");

async function seed() {
  const t = await makeApp({ now: () => NOW });
  await t.app.request("/api/flags"); // first request creates the tables
  const px = (symbol: string, date: string, close: number) =>
    t.db
      .prepare(
        "insert into stock_history (symbol, exchange, date, open, high, low, close, prev_close, volume) values (?, 'NSE', ?, ?, ?, ?, ?, ?, 1)",
      )
      .bind(symbol, date, close, close, close, close, close)
      .run();
  const call = (symbol: string, day: string, kind: string) =>
    t.db
      .prepare(
        "insert into analyse_calls (key, symbol, day, call, chance_pct, source, summary_en, summary_bn, reasons, risks, model, note, stored_at) values (?,?,?,?,?, 'code', null, null, '[]', '[]', null, null, 'x')",
      )
      .bind(`${symbol}|${day}`, symbol, day, kind, 60)
      .run();
  // Called 2026-08-01, scored 2026-10-31 (91 days). The Nifty rose 10%.
  for (const [d, n] of [
    ["2026-08-01", 100],
    ["2026-10-31", 110],
  ] as const)
    await px("NIFTY 50", d, n);
  await px("MISS", "2026-08-01", 100); //   +5%: a Buy behind the Nifty: missed
  await px("MISS", "2026-10-31", 105);
  await px("HIT", "2026-08-01", 100); //    +30%: a Buy ahead of the Nifty: not missed
  await px("HIT", "2026-10-31", 130);
  await px("AVD", "2026-08-01", 100); //    +40%: an Avoid that went up: missed
  await px("AVD", "2026-10-31", 140);
  await px("WTC", "2026-08-01", 100); //    a Watch is never scored
  await px("WTC", "2026-10-31", 50);
  await call("MISS", "2026-08-01", "buy");
  await call("HIT", "2026-08-01", "buy");
  await call("AVD", "2026-08-01", "avoid");
  await call("WTC", "2026-08-01", "watch");
  return t;
}

const row = (call_key: string, symbol: string, call: string, over = {}) => ({
  call_key,
  symbol,
  day: "2026-08-01",
  call,
  excess_pct: -5,
  cause: "unknown",
  why_en: "It lagged.",
  why_bn: "পিছিয়ে ছিল।",
  evidence: ["result"],
  source: "code",
  model: null,
  ...over,
});

it("C-089-1 only a missed Buy or Avoid is due, once its three months are over", async () => {
  const t = await seed();
  const due = (await (await t.signed("GET", "/api/postmortem/due")).json()) as {
    calls: { symbol: string; excess_pct: number; end_day: string }[];
  };
  expect(due.calls.map((c) => c.symbol).sort()).toEqual(["AVD", "MISS"]);
  expect(due.calls.find((c) => c.symbol === "MISS")?.excess_pct).toBe(-5);
  expect(due.calls[0]?.end_day).toBe("2026-10-31");
});

it("C-089-1 a missed call gets one post-mortem row, and a second write is ignored", async () => {
  const t = await seed();
  const first = await t.signed("POST", "/api/postmortem/row", row("MISS|2026-08-01", "MISS", "buy"));
  expect((await first.json()) as { written: number }).toEqual({ written: 1 });
  const again = await t.signed(
    "POST",
    "/api/postmortem/row",
    row("MISS|2026-08-01", "MISS", "buy", { why_en: "Changed." }),
  );
  expect((await again.json()) as { written: number }).toEqual({ written: 0 });
  const list = (await (await t.app.request("/api/postmortems?symbol=miss")).json()) as {
    postmortems: { why_en: string }[];
  };
  expect(list.postmortems).toHaveLength(1);
  expect(list.postmortems[0]?.why_en).toBe("It lagged.");
  const due = (await (await t.signed("GET", "/api/postmortem/due")).json()) as {
    calls: { symbol: string }[];
  };
  expect(due.calls.map((c) => c.symbol)).toEqual(["AVD"]);
});

it("C-089-1 a post-mortem without Bengali is refused", async () => {
  const t = await seed();
  const res = await t.signed(
    "POST",
    "/api/postmortem/row",
    row("MISS|2026-08-01", "MISS", "buy", { why_bn: "It lagged." }),
  );
  expect(res.status).toBe(422);
});
