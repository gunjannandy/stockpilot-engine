// MONEY's computed routes, behind sign-in. Lots are rebuilt from the stored trades on every call (nothing is
// cached or written, except the USD/INR rates the ITR route also refreshes); no broker is called.
import { TaxResponse } from "@stockpilot/contract";
import { Hono } from "hono";
import {
  fyLabel,
  incomeTax,
  inputs,
  MissingRate,
  netGains,
  realise,
  rulesFor,
  type TaxLot,
  type TaxSale,
} from "../../../money/src/tax/tax";
import type { Ctx } from "../app";
import { loadRateOn } from "../fx/rates";
import { loadRebuild } from "../lots/load";

export default function routes(ctx: Ctx) {
  const app = new Hono();

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
      return c.json(
        TaxResponse.parse({
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
  return app;
}
