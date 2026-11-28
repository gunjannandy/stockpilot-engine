import { expect, it } from "vitest";
import { budgetFor, istMonth, spentIn } from "./plan";

const t = (side: string, d: string, q: number, p: number | null, kind = "stock") => ({
  kind,
  side,
  trade_date: d,
  quantity: q,
  price: p,
});

it("counts only this month's stock and fund buys", () => {
  const rows = [
    t("buy", "2026-11-03", 10, 100),
    t("buy", "2026-11-20", 2, 500, "mf"),
    t("sell", "2026-11-21", 5, 900),
    t("buy", "2026-10-30", 9, 100),
    t("vest", "2026-11-05", 4, null, "rsu"),
    t("buy", "2026-11-06", 1, null),
  ];
  expect(spentIn(rows, "2026-11")).toBe(2000);
});

it("a month's own budget beats the default; none set is null", () => {
  expect(budgetFor({ default: 5, months: { "2026-11": 9 } }, "2026-11")).toBe(9);
  expect(budgetFor({ default: 5, months: {} }, "2026-11")).toBe(5);
  expect(budgetFor(null, "2026-11")).toBeNull();
});

it("month is the Indian one", () => {
  expect(istMonth(new Date("2026-11-30T20:00:00Z"))).toBe("2026-12");
});
