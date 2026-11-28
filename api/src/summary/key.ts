// The nightly note task's own key. It is a secret of the Worker (`NOTE_TASK_KEY`), separate from the Job ingest key and
// from a person's sign-in, so the one private model exception can read the summary and write its note and nothing else.
import type { MiddlewareHandler } from "hono";
import type { Ctx } from "../app";

const enc = new TextEncoder();

/** Constant-time compare of two strings (equal length first, then every byte). */
export function sameKey(a: string, b: string): boolean {
  const x = enc.encode(a);
  const y = enc.encode(b);
  if (x.length !== y.length) return false;
  let d = 0;
  for (let i = 0; i < x.length; i++) d |= (x[i] ?? 0) ^ (y[i] ?? 0);
  return d === 0;
}

/** Refuses with 401 unless `x-task-key` is the Worker's `NOTE_TASK_KEY`. With no key set the route is closed for everyone. */
export function taskKey(ctx: Ctx): MiddlewareHandler {
  return async (c, next) => {
    const want = (ctx.env as Record<string, string | undefined>).NOTE_TASK_KEY ?? "";
    const given = c.req.header("x-task-key") ?? "";
    if (want.length < 24 || !sameKey(want, given)) return c.json({ error: "no" }, 401);
    await next();
  };
}
