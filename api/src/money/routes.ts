// MONEY's computed routes, behind sign-in. Lots are rebuilt from the stored trades on every call (nothing is
// cached or written, except the USD/INR rates the ITR route also refreshes); no broker is called.
import {
  CalendarResponse,
  DividendsPost,
  HeldSymbols,
  RiskResponse,
  RsuResponse,
  TaxResponse,
  UsPricesPost,
  UsSymbols,
  XirrResponse,
} from "@stockpilot/contract";
import { Hono } from "hono";
import { concentration, type Exposure, niftyShock } from "../../../money/src/risk/risk";
import { expectedVests, type RsuLot, rsuView, type Vest } from "../../../money/src/rsu/rsu";
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
import { type Ctx, rawBody } from "../app";
import { loadRateOn, refreshRates } from "../fx/rates";
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

  // Concentration and the Nifty −10% view over held INR stocks at the newest close. Sector comes from the newest
  // `facts` row; beta is not stored yet, so every stock moves with the market (beta 1) and the response says so.
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
    const sectorOf = async (symbol: string): Promise<string | null> => {
      try {
        const row = (await ctx.d1
          .prepare("select sector from facts where symbol = ? order by as_of desc limit 1")
          .bind(symbol)
          .first()) as { sector?: string | null } | null;
        return row?.sector ? String(row.sector) : null;
      } catch {
        return null; // facts not stored yet
      }
    };
    for (const [symbol, q] of qty) {
      if (q <= 1e-9) continue;
      const p = await latestClose(symbol);
      if (!p) {
        warnings.push(`No price for ${symbol}.`);
        continue;
      }
      items.push({ symbol, sector: await sectorOf(symbol), value: q * p.close, beta: null });
    }
    return c.json(
      RiskResponse.parse({
        concentration: concentration(items),
        shock: niftyShock(items),
        warnings,
      }),
    );
  });

  app.post("/api/money/us-prices", ctx.guard.ingest, async (c) => {
    let body: unknown;
    try {
      body = JSON.parse(rawBody(c));
    } catch {
      return c.json({ error: "bad body" }, 400);
    }
    const post = UsPricesPost.safeParse(body);
    if (!post.success) return c.json({ error: "bad body" }, 400);
    for (const r of post.data.rows)
      await ctx.d1
        .prepare("insert or replace into us_prices (symbol, date, close) values (?, ?, ?)")
        .bind(post.data.symbol.toUpperCase(), r.date, r.close)
        .run();
    return c.json({ stored: post.data.rows.length });
  });

  // What the Job needs to ask for: dollar symbols still held, and where to start prices and USD/INR.
  app.get("/api/money/us-symbols", ctx.guard.ingest, async (c) => {
    const built = await loadRebuild(ctx.d1, {});
    const open = built.lots.filter(
      (l) => l.currency !== "INR" && l.quantity - l.closedQuantity > 1e-9,
    );
    const first = open.map((l) => l.acquiredOn).sort()[0] ?? ctx.now().toISOString().slice(0, 10);
    return c.json(
      UsSymbols.parse({
        symbols: [...new Set(open.map((l) => l.symbol))].sort(),
        since: first,
        fx_since: first,
      }),
    );
  });

  // The Job asks for USD/INR to be filled up to today, from the free ECB feed (best effort, rows added).
  app.post("/api/money/fx-refresh", ctx.guard.ingest, async (c) => {
    const today = ctx.now().toISOString().slice(0, 10);
    let since = today;
    try {
      const body = JSON.parse(rawBody(c)) as { since?: unknown };
      if (typeof body.since === "string" && /^\d{4}-\d{2}-\d{2}$/.test(body.since))
        since = body.since;
    } catch {}
    return c.json({ added: await refreshRates(ctx.d1, today, since) });
  });

  // The dollar holding (RSUs and any other USD lot) valued at the newest stored close and rate. Tax assumes the
  // top slab on a short-term gain and the long-term rate after 24 months, as for unlisted foreign shares.
  app.get("/api/money/rsu", ctx.guard.person, async (c) => {
    const today = ctx.now().toISOString().slice(0, 10);
    const rateOn = await loadRateOn(ctx.d1);
    const built = await loadRebuild(ctx.d1, { rateOn });
    const warnings: string[] = [];
    const fx = (await ctx.d1
      .prepare("select day, usd_inr from fx_rates order by day desc limit 1")
      .first()) as { day: string; usd_inr: number } | null;
    const rules = rulesFor(Number(today.slice(0, 4)) - (today.slice(5) < "04-01" ? 1 : 0));
    const topSlab = rules.slabs[rules.slabs.length - 1]?.[1] ?? 0.3;
    const open = built.lots.filter(
      (l) => l.currency !== "INR" && l.quantity - l.closedQuantity > 1e-9,
    );
    const symbols = [...new Set(open.map((l) => l.symbol))].sort();
    if (symbols.length && !fx) warnings.push("No USD/INR rate stored yet.");
    const out = [];
    for (const symbol of symbols) {
      const mine = open.filter((l) => l.symbol === symbol);
      const lots: RsuLot[] = mine.map((l) => ({
        acquiredOn: l.acquiredOn,
        quantity: l.quantity - l.closedQuantity,
        costUsd: l.costPerUnit || null,
        estimated: l.estimated,
      }));
      const p = (await ctx.d1
        .prepare("select date, close from us_prices where symbol = ? order by date desc limit 1")
        .bind(symbol)
        .first()) as { date: string; close: number } | null;
      if (!p) warnings.push(`No price for ${symbol}.`);
      const view =
        p && fx
          ? rsuView({
              lots,
              priceUsd: p.close,
              rate: fx.usd_inr,
              rateOn: (d) => rateOn?.(d) ?? null,
              rule: { longTermDays: 730, shortRate: topSlab, longRate: rules.ltcg_other_rate },
              asOf: today,
            })
          : null;
      const confirmed: Vest[] = mine
        .filter((l) => !l.estimated)
        .map((l) => ({
          day: l.acquiredOn,
          quantity: l.quantity,
          priceUsd: l.costPerUnit || null,
          status: "confirmed" as const,
        }));
      const through = `${Number(today.slice(0, 4)) + 1}${today.slice(4)}`;
      out.push({
        symbol,
        priceUsd: p?.close ?? null,
        priceDate: p?.date ?? null,
        view,
        expectedVests: expectedVests(confirmed, through).map((v) => ({
          day: v.day,
          quantity: v.quantity,
        })),
      });
    }
    return c.json(
      RsuResponse.parse({
        as_of: fx?.day ?? null,
        symbols: out,
        usdInr: fx?.usd_inr ?? null,
        warnings,
      }),
    );
  });

  const heldInr = async () => {
    const built = await loadRebuild(ctx.d1, {});
    const held = new Map<string, number>();
    let first = ctx.now().toISOString().slice(0, 10);
    for (const l of built.lots) {
      const q = l.quantity - l.closedQuantity;
      if (l.currency !== "INR" || l.kind !== "stock" || q <= 1e-9) continue;
      held.set(l.symbol, (held.get(l.symbol) ?? 0) + q);
      if (l.acquiredOn < first) first = l.acquiredOn;
    }
    return { held, first };
  };

  app.get("/api/money/held-symbols", ctx.guard.ingest, async (c) => {
    const { held, first } = await heldInr();
    return c.json(HeldSymbols.parse({ symbols: [...held.keys()].sort(), since: first }));
  });

  app.post("/api/money/dividends", ctx.guard.ingest, async (c) => {
    let body: unknown;
    try {
      body = JSON.parse(rawBody(c));
    } catch {
      return c.json({ error: "bad body" }, 400);
    }
    const post = DividendsPost.safeParse(body);
    if (!post.success) return c.json({ error: "bad body" }, 400);
    for (const r of post.data.rows)
      await ctx.d1
        .prepare("insert or replace into dividends (symbol, ex_date, per_share) values (?, ?, ?)")
        .bind(post.data.symbol.toUpperCase(), r.ex_date, r.per_share)
        .run();
    return c.json({ stored: post.data.rows.length });
  });

  // Dated corporate actions for held stocks, and expected dividend cash: each ex-date of the last year,
  // one year on, times the shares held now. An estimate; the company may pay more, less or nothing.
  app.get("/api/money/calendar", ctx.guard.person, async (c) => {
    const today = ctx.now().toISOString().slice(0, 10);
    const { held } = await heldInr();
    const warnings: string[] = [];
    const rows = async (sql: string, ...args: unknown[]) =>
      (
        (await ctx.d1
          .prepare(sql)
          .bind(...args)
          .all()) as { results?: Record<string, unknown>[] }
      ).results ?? [];
    const actions = (
      await rows(
        "select date, kind, symbol, old_shares, new_shares, new_symbol, reason from calendar where date >= ? and kind != 'holiday' and symbol is not null order by date, symbol",
        today,
      )
    )
      .filter((r) => held.has(String(r.symbol)))
      .map((r) => ({
        date: String(r.date),
        kind: String(r.kind),
        symbol: String(r.symbol),
        detail:
          r.new_symbol != null
            ? `now ${r.new_symbol}`
            : r.old_shares != null
              ? `${r.old_shares} to ${r.new_shares}`
              : ((r.reason as string | null) ?? null),
      }));
    const yearAgo = `${Number(today.slice(0, 4)) - 1}${today.slice(4)}`;
    const dividends = (
      await rows(
        "select symbol, ex_date, per_share from dividends where ex_date > ? and ex_date <= ? order by ex_date, symbol",
        yearAgo,
        today,
      )
    )
      .filter((r) => held.has(String(r.symbol)))
      .map((r) => {
        const shares = held.get(String(r.symbol)) ?? 0;
        const perShare = Number(r.per_share);
        return {
          date: `${Number(String(r.ex_date).slice(0, 4)) + 1}${String(r.ex_date).slice(4)}`,
          symbol: String(r.symbol),
          perShare,
          shares,
          cash: Math.round(perShare * shares * 100) / 100,
        };
      })
      .filter((d) => d.date >= today);
    if (held.size && dividends.length === 0)
      warnings.push("No dividend history stored for the stocks held.");
    return c.json(
      CalendarResponse.parse({
        as_of: today,
        actions,
        dividends,
        expectedCash: Math.round(dividends.reduce((s, d) => s + d.cash, 0) * 100) / 100,
        warnings,
      }),
    );
  });
  return app;
}
