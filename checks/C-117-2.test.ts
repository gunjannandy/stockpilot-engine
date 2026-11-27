// C-117-2: the calendar Job posts holidays and corporate actions; health is amber with under 30 days ahead.
import { expect, it } from "vitest";
import { HEALTH, makeApp } from "../api/src/testkit";

const NOW = () => new Date("2026-11-27T03:30:00Z"); // 09:00 IST
const prov = (run_id: string) => ({
  dataset: "calendar",
  run_id,
  source: "nse+bse",
  fetched_at: "2026-11-27T08:55:00+05:30",
  as_of: "2026-11-27",
});
const blank = { reason: null, symbol: null, old_shares: null, new_shares: null, new_symbol: null };
const holiday = (date: string, n: number) => ({
  ...blank,
  id: `h-${n}`,
  kind: "holiday",
  date,
  reason: "Holiday",
});

async function post(t: Awaited<ReturnType<typeof makeApp>>, run_id: string, rows: unknown[]) {
  const a = await t.signed("POST", "/api/publish/rows", { ...prov(run_id), rows });
  expect(a.status).toBe(200);
  const f = await t.signed("POST", "/api/publish/finish", { dataset: "calendar", run_id });
  return (await f.json()) as { published: boolean };
}
const status = async (t: Awaited<ReturnType<typeof makeApp>>) =>
  (await (
    await t.app.request("/api/calendar/status", { headers: { "x-health-secret": HEALTH } })
  ).json()) as { status: string; days_ahead: number; covered_until: string | null };

it("C-117-2 an empty calendar is amber", async () => {
  const t = await makeApp({ now: NOW });
  expect((await status(t)).status).toBe("amber");
});

it("C-117-2 holidays and corporate actions post, and under 30 days ahead is amber", async () => {
  const t = await makeApp({ now: NOW });
  const rows = [
    holiday("2026-12-25", 1),
    {
      ...blank,
      id: "sp-1",
      kind: "split",
      date: "2026-12-10",
      symbol: "ABC",
      old_shares: 1,
      new_shares: 5,
    },
    {
      ...blank,
      id: "sc-1",
      kind: "symbol_change",
      date: "2026-12-05",
      symbol: "OLD",
      new_symbol: "NEW",
    },
  ];
  expect((await post(t, "cal-1", rows)).published).toBe(true);
  const s = await status(t);
  expect(s).toMatchObject({ status: "amber", covered_until: "2026-12-25", days_ahead: 28 });
});

it("C-117-2 30 or more days ahead is green, and the market status follows the posted holidays", async () => {
  const t = await makeApp({ now: NOW });
  await post(t, "cal-2", [holiday("2026-12-25", 1), holiday("2027-01-26", 2)]);
  expect(await status(t)).toMatchObject({ status: "green", covered_until: "2027-01-26" });
  const ask = async (date: string) => {
    const res = await t.app.request(`/api/market/status?date=${date}`, {
      headers: { "x-signature": await (await import("../api/src/app")).sign("k".repeat(40), "") },
    });
    return res.json();
  };
  expect(await ask("2026-12-25")).toEqual({
    date: "2026-12-25",
    is_trading_day: false,
    reason: "Holiday",
  });
  expect(await ask("2026-12-24")).toEqual({
    date: "2026-12-24",
    is_trading_day: true,
    reason: null,
  });
});

it("C-117-2 a row missing what its kind needs is held back", async () => {
  const t = await makeApp({ now: NOW });
  const res = await t.signed("POST", "/api/publish/rows", {
    ...prov("cal-5"),
    rows: [
      holiday("2027-01-26", 1),
      { ...blank, id: "x-1", kind: "split", date: "2026-12-10", symbol: "ABC" },
    ],
  });
  expect(await res.json()).toMatchObject({ accepted: 1, held_back: 1 });
});

it("C-117-2 a run with no holiday fails and the last good calendar stays", async () => {
  const t = await makeApp({ now: NOW });
  await post(t, "cal-3", [holiday("2027-01-26", 1)]);
  const bad = await post(t, "cal-4", [
    { ...blank, id: "d-1", kind: "delisting", date: "2026-12-01", symbol: "GONE" },
  ]);
  expect(bad.published).toBe(false);
  expect((await status(t)).covered_until).toBe("2027-01-26");
});
