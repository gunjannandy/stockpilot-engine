// ITR pack download: lots are rebuilt from the stored trades, the pack is built in memory and sent as one zip.
// Read-only: nothing is written and no broker is called.
import { Hono } from "hono";
import { buildPack, packZip } from "../../../money/src/itr";
import { rebuild } from "../../../money/src/lots/rebuild";
import type { Trade } from "../../../money/src/lots/types";
import type { TaxLot, TaxSale } from "../../../money/src/tax/tax";
import type { Ctx } from "../app";

type TradeRow = {
  source: string;
  source_ref: string;
  kind: string;
  symbol: string;
  isin: string | null;
  side: string;
  trade_date: string;
  quantity: number;
  price: number | null;
  currency: string;
  status: string;
  trade_key: string;
};

export function itrRoutes(ctx: Ctx) {
  const app = new Hono();

  app.get("/api/itr/pack", ctx.guard.person, async (c) => {
    const fy = Number(c.req.query("fy"));
    if (!Number.isInteger(fy) || fy < 2018 || fy > 2100) {
      return c.json({ error: "Pick a tax year, like 2026 for 2026-27." }, 400);
    }
    const res = (await ctx.d1
      .prepare(
        "select source, source_ref, kind, symbol, isin, side, trade_date, quantity, price, currency, status, trade_key from trades order by trade_date, rowid",
      )
      .all()) as { results?: TradeRow[] };
    const trades: Trade[] = (res.results ?? []).map((r) => ({
      source: r.source,
      sourceRef: r.source_ref,
      kind: r.kind,
      symbol: r.symbol,
      isin: r.isin,
      side: r.side,
      tradeDate: r.trade_date,
      quantity: r.quantity,
      price: r.price,
      currency: r.currency,
      status: r.status,
      tradeKey: r.trade_key,
    }));
    if (trades.length === 0) return c.json({ error: "No trades stored yet. Sync first." }, 404);
    const built = rebuild({ trades, actions: [] });
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
    const pack = buildPack({ lots, sales, fy, rateOn: null, closes: {} });
    const bytes = packZip(pack.files);
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
