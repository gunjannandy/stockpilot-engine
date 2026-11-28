// ITR pack download: lots are rebuilt from the stored trades, the pack is built in memory and sent as one zip.
// Writes only the cached USD/INR rates (fx_rates); no broker is called.
import { Hono } from "hono";
import { addDays } from "../../../money/src/core/dates";
import { buildPack, packZip } from "../../../money/src/itr";
import type { TaxLot, TaxSale } from "../../../money/src/tax/tax";
import { MissingRate } from "../../../money/src/tax/tax";
import { type Ctx, istDay } from "../app";
import { loadRateOn, refreshRates } from "../fx/rates";
import { loadRebuild } from "../lots/load";

export function itrRoutes(ctx: Ctx) {
  const app = new Hono();

  app.get("/api/itr/pack", ctx.guard.person, async (c) => {
    const fy = Number(c.req.query("fy"));
    if (!Number.isInteger(fy) || fy < 2018 || fy > 2100) {
      return c.json({ error: "Pick a tax year, like 2026 for 2026-27." }, 400);
    }
    const foreign = (await ctx.d1
      .prepare(
        "select min(d) as d from (select min(trade_date) as d from trades where currency <> 'INR' union all select min(acquired_on) from fidelity_lots)",
      )
      .all()) as { results?: { d: string | null }[] };
    const first = foreign.results?.[0]?.d;
    if (first) {
      const since = addDays(first.slice(0, 10), -45);
      await refreshRates(ctx.d1, istDay(ctx.now()), since).catch(() => 0);
    }
    const built = await loadRebuild(ctx.d1, { rateOn: await loadRateOn(ctx.d1) });
    if (built.lots.length === 0 && built.sales.length === 0)
      return c.json({ error: "No trades stored yet. Sync first." }, 404);
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
    let bytes: Uint8Array;
    try {
      const pack = buildPack({ lots, sales, fy, rateOn: await loadRateOn(ctx.d1), closes: {} });
      bytes = packZip(pack.files);
    } catch (e) {
      if (e instanceof MissingRate)
        return c.json(
          { error: "The dollar-rupee rate for a date is missing. Try again later." },
          409,
        );
      throw e;
    }
    return new Response(bytes, {
      headers: {
        "content-type": "application/zip",
        "content-disposition": `attachment; filename="tax-pack-${fy}-${String((fy + 1) % 100).padStart(2, "0")}.zip"`,
        "cache-control": "no-store",
      },
    });
  });

  return app;
}

export default function routes(ctx: Ctx) {
  return itrRoutes(ctx);
}
