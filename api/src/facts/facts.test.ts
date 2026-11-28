import type { FactsRow } from "@stockpilot/contract";
import { describe, expect, it } from "vitest";
import { makeApp } from "../testkit";

const row = (n: number, over: Partial<FactsRow> = {}): FactsRow => ({
  id: `NSE:S${n}`,
  symbol: `S${n}`,
  exchange: "NSE",
  name: `Stock ${n}`,
  sector: "Sector",
  as_of: "2026-11-28",
  pe: 20,
  pe_sector: 25,
  pb: 3,
  dividend_yield_pct: 1,
  market_cap_cr: 5000,
  sales_growth_yoy_pct: 10,
  profit_growth_yoy_pct: 12,
  roe_pct: 15,
  roce_pct: 18,
  debt_to_equity: 0.2,
  promoter_pct: 50,
  pledge_pct: 0,
  sentences_json:
    '[{"key":"pe","en":"Priced at 20 times a year\'s profit.","bn":"এক বছরের লাভের ২০ গুণ দামে চলছে।"}]',
  figures_json: '[{"metric":"sales","value":1200,"period":"2026-03-31","source":"nse"}]',
  not_available: "",
  ...over,
});

const stamp = {
  dataset: "facts",
  source: "nse filings",
  fetched_at: "2026-11-28T03:00:00+05:30",
  as_of: "2026-11-28",
};

async function publish(rows: unknown[]) {
  const t = await makeApp();
  const posted = await t.signed("POST", "/api/publish/rows", { ...stamp, run_id: "f1", rows });
  expect(posted.status).toBe(200);
  const fin = await t.signed("POST", "/api/publish/finish", { dataset: "facts", run_id: "f1" });
  return { t, fin, posted };
}

describe("facts route", () => {
  it("answers facts null before any run, and for an unknown stock", async () => {
    const { app } = await makeApp();
    const r = (await (await app.request("/api/facts/S1")).json()) as { facts: unknown };
    expect(r.facts).toBeNull();
  });

  it("gives one stock's metrics, sentences and raw figures", async () => {
    const { t, fin } = await publish(Array.from({ length: 120 }, (_, i) => row(i + 1)));
    expect(fin.status).toBe(200);
    const r = (await (await t.app.request("/api/facts/s7")).json()) as {
      facts: {
        symbol: string;
        pe_sector: number;
        sentences: { bn: string }[];
        figures: { source: string }[];
      };
    };
    expect(r.facts.symbol).toBe("S7");
    expect(r.facts.pe_sector).toBe(25);
    expect(r.facts.sentences[0]?.bn).toMatch(/[ঀ-৿]/);
    expect(r.facts.figures[0]?.source).toBe("nse");
    const none = (await (await t.app.request("/api/facts/NOPE")).json()) as { facts: unknown };
    expect(none.facts).toBeNull();
  });

  it("holds back a row with a sentence that has no Bengali, and fails a run under 100 stocks", async () => {
    const bad = row(1, { sentences_json: '[{"key":"pe","en":"x","bn":"x"}]' });
    const { posted, fin } = await publish([bad]);
    expect(((await posted.json()) as { held_back: number }).held_back).toBe(1);
    expect(fin.status).toBe(422);
  });
});
