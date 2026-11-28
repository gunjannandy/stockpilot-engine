// MONEY's computed routes, behind sign-in. Lots are rebuilt from the stored trades on every call (nothing is
// cached or written, except the USD/INR rates the ITR route also refreshes); no broker is called.
import { RiskResponse, TaxResponse, XirrResponse } from "@stockpilot/contract";
import { Hono } from "hono";
import { concentration, type Exposure, niftyShock } from "../../../money/src/risk/risk";
import {
  fyLabel,
  harvest,
  incomeTax,
  inputs,
  MissingRate,
  netGains,
  openLots,
  realise,
  rulesFor,
  type TaxLot,
  type TaxSale,
} from "../../../money/src/tax/tax";
import { type Flow, returnVsNifty, xirr } from "../../../money/src/xirr/xirr";
import type { Ctx } from "../app";
import { loadRateOn } from "../fx/rates";
import { loadRebuild } from "../lots/load";

export default function routes(ctx: Ctx) {
  const app = new Hono();

  const latestClose = async (symbol: string) =>
    (await ctx.d1
      .prepare("select date, close from stock_history where symbol = ? order by date desc limit 1")
      .bind(symbol)
      .first()) as { date: string; close: number } | null;

  app.get("/api/money/tax", ctx.guard.person, async (c) => {
    const fy = Number(c.req.query("fy"));
    if (!Number.isInteger(fy) || fy < 2018 || fy > 2100)
      return c.json({ error: "Pick a tax year, like 2026 for 2026-27." }, 400);
    const rateOn = await loadRateOn(ctx.d1);
    const built = await loadRebuild(ctx.d1, { rateOn });
    const lots: TaxLot[] = built.lots.map((l, i) => ({
      id: i + 1,
      symbol: l.symbol,
      isin: l.isin ?? l.symbol,
      kind: l.kind,
      acquired_on: l.acquiredOn,
      quantity: l.quantity,
      cost_per_unit: l.costPerUnit,
      currency: l.currency,
    }));
    const sales: TaxSale[] = built.sales.map((s) => ({
      symbol: s.symbol,
      isin: s.isin ?? s.symbol,
      sold_on: s.soldOn,
      quantity: s.quantity,
      price_per_unit: s.pricePerUnit,
      currency: s.currency,
    }));
    const rules = rulesFor(fy);
    try {
      const rows = realise(lots, sales, {}, rateOn).filter(
        (r) => r.sold_on >= `${fy}-04-01` && r.sold_on <= `${fy + 1}-03-31`,
      );
      const net = netGains(rows, rules, fy, null);
      const est = incomeTax(inputs(net), rules);
      // Harvest ideas use the newest stored close of each stock still held, and today's rules and date.
      const open = openLots(lots, sales);
      const prices: Record<string, number> = {};
      for (const sym of new Set(open.map((l) => l.symbol))) {
        const p = await latestClose(sym);
        if (p) prices[sym] = p.close;
      }
      const today = ctx.now().toISOString().slice(0, 10);
      const ideas = harvest(open, prices, today, rules, Math.max(net.ltcg_equity, 0));
      return c.json(
        TaxResponse.parse({
          harvest: ideas,
          fy,
          label: fyLabel(fy),
          rows,
          net,
          tax: { total: est.total, surcharge: est.surcharge, cess: est.cess },
          ltcg_equity_exempt: rules.ltcg_exempt,
          ltcg_equity_room_left: Math.max(rules.ltcg_exempt - net.ltcg_equity, 0),
          warnings: est.warnings,
        }),
      );
    } catch (e) {
      if (e instanceof MissingRate)
        return c.json(
          { error: "The dollar-rupee rate for a date is missing. Try again later." },
          409,
        );
      throw e;
    }
  });

  // Stock trades only (INR; dollar trades are valued on the RSU view). Today's value of what is still held
  // is the newest stored close; the Nifty is read from the same history table when it holds the index.
  app.get("/api/money/xirr", ctx.guard.person, async (c) => {
    const rows =
      (
        (await ctx.d1
          .prepare(
            "select symbol, side, trade_date, quantity, price from trades where kind = 'stock' and currency = 'INR' and status = 'confirmed' order by trade_date",
          )
          .all()) as { results?: Record<string, unknown>[] }
      ).results ?? [];
    const warnings: string[] = [];
    const close = async (symbol: string, day?: string) => {
      const r = (await ctx.d1
        .prepare(
          `select date, close from stock_history where symbol = ? ${day ? "and date <= ?" : ""} order by date desc limit 1`,
        )
        .bind(...(day ? [symbol, day] : [symbol]))
        .first()) as { date: string; close: number } | null;
      return r;
    };
    const bySymbol = new Map<string, { flows: Flow[]; qty: number }>();
    for (const r of rows) {
      const sym = String(r.symbol);
      const q = Number(r.quantity);
      const amt = q * Number(r.price);
      const e = bySymbol.get(sym) ?? { flows: [], qty: 0 };
      const buy = r.side === "buy";
      e.flows.push({ day: String(r.trade_date), amount: buy ? -amt : amt });
      e.qty += buy ? q : -q;
      bySymbol.set(sym, e);
    }
    let asOf: string | null = null;
    const all: Flow[] = [];
    let total = 0;
    let complete = true;
    const holdings = [];
    for (const [symbol, e] of bySymbol) {
      all.push(...e.flows);
      const last = e.qty > 1e-9 ? await close(symbol) : null;
      if (e.qty > 1e-9 && !last) {
        complete = false;
        warnings.push(`No price for ${symbol}.`);
      }
      const value = last ? e.qty * last.close : e.qty > 1e-9 ? null : 0;
      if (last && (!asOf || last.date > asOf)) asOf = last.date;
      total += value ?? 0;
      holdings.push({
        symbol,
        quantity: Math.max(e.qty, 0),
        value,
        xirr:
          value === null
            ? null
            : xirr([...e.flows, ...(value ? [{ day: last?.date ?? "", amount: value }] : [])]),
      });
    }
    const nifty = new Map<string, number>();
    for (const f of all) {
      const n = await close("NIFTY 50", f.day);
      if (n) nifty.set(f.day, n.close);
    }
    const end = asOf;
    const endNifty = end ? await close("NIFTY 50", end) : null;
    if (end && endNifty) nifty.set(end, endNifty.close);
    const ret =
      complete && end && all.length
        ? returnVsNifty(all, total, end, (d) => nifty.get(d) ?? null)
        : { holding: null, nifty: null, edge: null };
    return c.json(
      XirrResponse.parse({
        as_of: asOf,
        portfolio: { xirr: ret.holding, nifty: ret.nifty, edge: ret.edge },
        holdings,
        warnings,
      }),
    );
  });

  // Concentration and the Nifty −10% view over held INR stocks at the newest close. Sector and beta are not
  // stored yet, so every stock is "Unknown" and moves with the market (beta 1); the response says so.
  app.get("/api/money/risk", ctx.guard.person, async (c) => {
    const rows =
      (
        (await ctx.d1
          .prepare(
            "select symbol, side, quantity from trades where kind = 'stock' and currency = 'INR' and status = 'confirmed'",
          )
          .all()) as { results?: Record<string, unknown>[] }
      ).results ?? [];
    const qty = new Map<string, number>();
    for (const r of rows)
      qty.set(
        String(r.symbol),
        (qty.get(String(r.symbol)) ?? 0) + (r.side === "buy" ? 1 : -1) * Number(r.quantity),
      );
    const items: Exposure[] = [];
    const warnings: string[] = [];
    for (const [symbol, q] of qty) {
      if (q <= 1e-9) continue;
      const p = await latestClose(symbol);
      if (!p) {
        warnings.push(`No price for ${symbol}.`);
        continue;
      }
      items.push({ symbol, sector: null, value: q * p.close, beta: null });
    }
    return c.json(
      RiskResponse.parse({
        concentration: concentration(items),
        shock: niftyShock(items),
        warnings,
      }),
    );
  });
  return app;
}
