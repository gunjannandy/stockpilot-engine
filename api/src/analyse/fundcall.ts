// Fund Analyse: the Job's read of one fund's public inputs, its write of one call per fund and day, and the person's
// read. Nothing here knows what anyone holds; the card adds switching cost and tax lines in the browser.
import { analyseCallCheck, FundAnalyseCall } from "@stockpilot/contract";
import { Hono } from "hono";
import { type Ctx, istText, rawBody } from "../app";
import { loadFundCalls } from "../fundcalls/routes";

const FUND_ID = /^[A-Za-z0-9][A-Za-z0-9:_.-]{0,60}$/;
type Stored = Record<string, unknown> & { reasons: string; risks: string };

export function fundcallRoutes(ctx: Ctx) {
  const app = new Hono();

  app.get("/api/fundcall/inputs/:id", ctx.guard.ingest, async (c) => {
    const id = c.req.param("id");
    if (!FUND_ID.test(id)) return c.json({ error: "bad id" }, 400);
    const p = (await ctx.d1
      .prepare("select run_id from pointers where dataset = 'funds'")
      .first()) as { run_id: string } | null;
    const row = p
      ? ((await ctx.d1
          .prepare(
            "select body from dataset_rows where dataset = 'funds' and run_id = ? and json_extract(body, '$.id') = ? limit 1",
          )
          .bind(p.run_id, id)
          .first()) as { body: string } | null)
      : null;
    const { navs_json: _navs, ...fund } = row ? JSON.parse(row.body) : { navs_json: "" };
    const calls = await loadFundCalls(ctx);
    return c.json({
      fund: row ? fund : null,
      call: calls.rows.find((r) => r.kind === "call" && r.id === id) ?? null,
    });
  });

  app.post("/api/fundcall/call", ctx.guard.ingest, async (c) => {
    let body: unknown;
    try {
      body = JSON.parse(rawBody(c));
    } catch {
      return c.json({ error: "bad body" }, 400);
    }
    const req = FundAnalyseCall.safeParse(body);
    if (!req.success) return c.json({ error: "bad body" }, 400);
    const k = req.data;
    const refused = analyseCallCheck({ ...k, symbol: "FUND" });
    if (refused) return c.json({ error: refused }, 422);
    await ctx.d1
      .prepare(
        "insert or replace into fund_analyse_calls (key, fund, day, call, chance_pct, source, summary_en, summary_bn, reasons, risks, model, note, stored_at) values (?,?,?,?,?,?,?,?,?,?,?,?,?)",
      )
      .bind(
        `${k.fund}|${k.day}`,
        k.fund,
        k.day,
        k.call,
        k.chance_pct,
        k.source,
        k.summary_en,
        k.summary_bn,
        JSON.stringify(k.reasons),
        JSON.stringify(k.risks),
        k.model,
        k.note,
        istText(ctx.now()),
      )
      .run();
    return c.json({ ok: true });
  });

  app.get("/api/fundcall/:id", ctx.guard.person, async (c) => {
    const id = c.req.param("id");
    const r = (await ctx.d1
      .prepare(
        "select fund, day, call, chance_pct, source, summary_en, summary_bn, reasons, risks, model, note, stored_at from fund_analyse_calls where fund = ? order by day desc limit 1",
      )
      .bind(id)
      .first()) as Stored | null;
    return c.json({
      fund: id,
      call: r ? { ...r, reasons: JSON.parse(r.reasons), risks: JSON.parse(r.risks) } : null,
    });
  });

  return app;
}
