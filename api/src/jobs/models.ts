// The model gate (decisions §2 Models): a daily budget per Job kind and an answer cache keyed by
// brief, model and day. A repeat brief costs nothing; past the cap a model Job is refused and the
// pane says "Next update tomorrow".
import { istDay, istText } from "../app";
import type { Core } from "./runtime";

/** Model calls a kind may start in one IST day. Kinds not listed here may not call a model. */
export const MODEL_DAILY_CAP: Record<string, number> = {
  analyse: 60,
  refresh_call: 120,
  news_tag: 200,
  news_rank: 100,
  nightly: 400,
};
export const NEXT_UPDATE_TOMORROW = "Next update tomorrow";

const hex = (buf: ArrayBuffer) =>
  [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
export async function cacheKey(kind: string, model: string, brief: string, day: string) {
  const data = new TextEncoder().encode(`${kind}\n${model}\n${brief}\n${day}`);
  return hex(await crypto.subtle.digest("SHA-256", data));
}

export type Claim =
  | { cached: true; answer: string }
  | { cached: false; allowed: true; left: number }
  | { cached: false; allowed: false };

export async function claimModel(
  ctx: Core,
  caps: Record<string, number>,
  a: { kind: string; model: string; brief: string },
): Promise<Claim> {
  const day = istDay(ctx.now());
  const hit = (await ctx.d1
    .prepare("select answer from model_cache where key = ?")
    .bind(await cacheKey(a.kind, a.model, a.brief, day))
    .first()) as { answer: string } | null;
  if (hit) return { cached: true, answer: hit.answer };
  const cap = caps[a.kind] ?? 0;
  await ctx.d1
    .prepare("insert or ignore into model_usage (day, kind, used) values (?, ?, 0)")
    .bind(day, a.kind)
    .run();
  // One statement takes the slot only while one is left, so two Jobs cannot both take the last.
  const took = await ctx.d1
    .prepare("update model_usage set used = used + 1 where day = ? and kind = ? and used < ?")
    .bind(day, a.kind, cap)
    .run();
  if (took.meta.changes === 0) return { cached: false, allowed: false };
  const used = (await ctx.d1
    .prepare("select used from model_usage where day = ? and kind = ?")
    .bind(day, a.kind)
    .first()) as { used: number };
  return { cached: false, allowed: true, left: cap - used.used };
}

export async function storeAnswer(
  ctx: Core,
  a: { kind: string; model: string; brief: string; answer: string },
) {
  const day = istDay(ctx.now());
  await ctx.d1
    .prepare(
      "insert or replace into model_cache (key, kind, day, answer, at) values (?, ?, ?, ?, ?)",
    )
    .bind(await cacheKey(a.kind, a.model, a.brief, day), a.kind, day, a.answer, istText(ctx.now()))
    .run();
  // Yesterday's answers are never read again (the key carries the day).
  await ctx.d1.prepare("delete from model_cache where day < ?").bind(day).run();
}

export async function modelStatus(ctx: Core, caps: Record<string, number>, kind: string) {
  const day = istDay(ctx.now());
  const row = (await ctx.d1
    .prepare("select used from model_usage where day = ? and kind = ?")
    .bind(day, kind)
    .first()) as { used: number } | null;
  const used = row?.used ?? 0;
  const cap = caps[kind] ?? 0;
  const left = Math.max(0, cap - used);
  return { kind, day, used, cap, left, message: left === 0 ? NEXT_UPDATE_TOMORROW : null };
}
