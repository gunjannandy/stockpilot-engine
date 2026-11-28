// Calls: the append-only door (the forecast Job only), the latest call per stock, one stock's history, compare, and
// the scored past calls the confidence line is built from. A call row is only ever inserted: a second write of the same
// id is ignored, and no code updates or deletes one (checks/C-035-1 scans this folder).
import {
  type CallHistoryResponse,
  type CallRow,
  CallsRequest,
  type CallsResponse,
  type CallView,
  type CompareResponse,
  callRowCheck,
  confidenceLine,
} from "@stockpilot/contract";
import { Hono } from "hono";
import { type Ctx, rawBody } from "../app";

type Raw = Omit<CallRow, "limited"> & { limited: number };
const COLUMNS =
  "id, symbol, exchange, made_on, verdict, chance, horizon_days, base_cases, base_rate, sell_line, buy_line, could_rise_to, would_buy_at, sell_at_once_at, limited, sentences_json, similar_n, similar_beat, model_version";
const view = (r: Raw): CallView => ({
  ...r,
  limited: r.limited === 1,
  confidence: confidenceLine(r.similar_n, r.similar_beat),
});

export default function routes(ctx: Ctx) {
  const app = new Hono();

  /** The newest call of each stock (the screen reads the latest; older rows stay as the record). */
  const latest = async (symbols?: string[]): Promise<CallView[]> => {
    const where = symbols?.length ? `where c.symbol in (${symbols.map(() => "?").join(",")})` : "";
    const r = (await ctx.d1
      .prepare(
        `select ${COLUMNS.split(", ")
          .map((x) => `c.${x}`)
          .join(
            ", ",
          )} from calls c join (select exchange, symbol, max(made_on) as m from calls group by exchange, symbol) l on l.exchange = c.exchange and l.symbol = c.symbol and l.m = c.made_on ${where} order by c.symbol, c.horizon_days`,
      )
      .bind(...(symbols ?? []))
      .all()) as { results: Raw[] };
    return r.results.map(view);
  };

  app.post("/api/calls/publish", ctx.guard.ingest, async (c) => {
    let body: unknown;
    try {
      body = JSON.parse(rawBody(c));
    } catch {
      return c.json({ error: "bad body" }, 400);
    }
    const req = CallsRequest.safeParse(body);
    if (!req.success) return c.json({ error: "bad body" }, 400);
    const held: { id: string; reason: string }[] = [];
    const ok = req.data.rows.filter((r) => {
      const reason = callRowCheck(r);
      if (reason) held.push({ id: r.id, reason });
      return !reason;
    });
    let written = 0;
    for (const r of ok) {
      const res = (await ctx.d1
        .prepare(
          `insert or ignore into calls (${COLUMNS}) values (${COLUMNS.split(", ")
            .map(() => "?")
            .join(",")})`,
        )
        .bind(
          r.id,
          r.symbol,
          r.exchange,
          r.made_on,
          r.verdict,
          r.chance,
          r.horizon_days,
          r.base_cases,
          r.base_rate,
          r.sell_line,
          r.buy_line,
          r.could_rise_to,
          r.would_buy_at,
          r.sell_at_once_at,
          r.limited ? 1 : 0,
          r.sentences_json,
          r.similar_n,
          r.similar_beat,
          r.model_version,
        )
        .run()) as { meta?: { changes?: number } };
      written += res.meta?.changes ?? 0;
    }
    return c.json({ written, ignored: ok.length - written, held });
  });

  /** Past calls whose window has ended, with whether they beat the Nifty: the confidence line's source. */
  app.get("/api/calls/scored", ctx.guard.ingest, async (c) => {
    const r = (await ctx.d1
      .prepare(
        "select c.made_on, c.verdict, c.chance, c.horizon_days, s.beat from calls c join call_scores s on s.call_id = c.id where c.chance is not null order by c.made_on desc limit 5000",
      )
      .all()) as { results: { beat: number }[] };
    return c.json({ rows: r.results.map((x) => ({ ...x, beat: x.beat === 1 })) });
  });

  app.get("/api/calls", ctx.guard.person, async (c) => {
    const calls = await latest();
    const out: CallsResponse = {
      as_of: calls.reduce<string | null>((m, x) => (m && m > x.made_on ? m : x.made_on), null),
      calls,
    };
    return c.json(out);
  });

  app.get("/api/calls/compare", ctx.guard.person, async (c) => {
    const a = (c.req.query("a") ?? "").toUpperCase();
    const b = (c.req.query("b") ?? "").toUpperCase();
    if (!a || !b) return c.json({ error: "give a and b" }, 400);
    const both = await latest([a, b]);
    const out: CompareResponse = {
      a: both.find((x) => x.symbol === a) ?? null,
      b: both.find((x) => x.symbol === b) ?? null,
    };
    return c.json(out);
  });

  app.get("/api/calls/:symbol", ctx.guard.person, async (c) => {
    const symbol = c.req.param("symbol").toUpperCase();
    const r = (await ctx.d1
      .prepare(
        `select ${COLUMNS} from calls where symbol = ? order by made_on desc, horizon_days limit 200`,
      )
      .bind(symbol)
      .all()) as { results: Raw[] };
    const out: CallHistoryResponse = { symbol, calls: r.results.map(view) };
    return c.json(out);
  });

  return app;
}
