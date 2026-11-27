// The one Worker's app: shared types, the guards, and `createApp`. No area edits this file:
// routes, schema files, migrations and production checks are found by folder (api/migrate/discover.ts).

import { CONTRACT_HEADER, CONTRACT_VERSION } from "@stockpilot/contract";
import { drizzle } from "drizzle-orm/d1";
import { type Context, Hono, type MiddlewareHandler } from "hono";
import * as core from "../drizzle/core";
import { applyPending, type Migration } from "../migrate/run";

export type Env = {
  INGEST_HMAC_KEY?: string;
  HEALTH_SECRET?: string;
  APP_VERSION?: string;
};

// biome-ignore lint/suspicious/noExplicitAny: D1Database (Workers) and SqliteD1 (Node) both fit this shape
export type D1Like = any;
export type Db = ReturnType<typeof drizzle<typeof core>>;

export type CheckOutcome = { ok: boolean; detail: string };
export type ProductionCheck = {
  id: string;
  /** Run after all the others (the check that audits the runner itself). */
  last?: boolean;
  run(ctx: Ctx, run: { startedAt: string }): Promise<CheckOutcome>;
};
export type AreaModule = {
  name: string;
  routes?: (ctx: Ctx) => Hono;
  checks?: ProductionCheck[];
};
export type BuildInfo = { productionDb: string; previewDb: string };
export type Registry = { areas: AreaModule[]; migrations: Migration[]; buildInfo?: BuildInfo };

export type Ctx = {
  d1: D1Like;
  db: Db;
  env: Env;
  version: string;
  registry: Registry;
  now: () => Date;
  /** The app's own door, for checks that call routes as a client would. */
  call: (path: string, init?: RequestInit) => Promise<Response>;
  guard: { ingest: MiddlewareHandler; secret: MiddlewareHandler; person: MiddlewareHandler };
  /** Sign-in installs the real person guard here. Guards already handed to areas pick it up at once. */
  setPersonGuard: (guard: MiddlewareHandler) => void;
};

const enc = new TextEncoder();
const IST_MS = 5.5 * 3600 * 1000;

export const istText = (d: Date) =>
  `${new Date(d.getTime() + IST_MS).toISOString().slice(0, 19)}+05:30`;
export const istDay = (d: Date) => new Date(d.getTime() + IST_MS).toISOString().slice(0, 10);

const hex = (buf: ArrayBuffer) =>
  [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");

async function hmacKey(secret: string, usage: KeyUsage[]) {
  return crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    usage,
  );
}
/** The signature Jobs and workflows send in `x-signature`: HMAC-SHA256 hex over the raw body. */
export async function sign(secret: string, body: string): Promise<string> {
  return hex(await crypto.subtle.sign("HMAC", await hmacKey(secret, ["sign"]), enc.encode(body)));
}
async function signatureOk(secret: string | undefined, given: string, body: string) {
  if (!secret || secret.length < 32 || !/^[0-9a-f]{64}$/.test(given)) return false;
  const bytes = Uint8Array.from(given.match(/../g) ?? [], (h) => Number.parseInt(h, 16));
  // verify compares in constant time
  return crypto.subtle.verify("HMAC", await hmacKey(secret, ["verify"]), bytes, enc.encode(body));
}
/** Constant-time string compare: both sides are hashed to equal length first. */
async function sameSecret(expected: string | undefined, given: string | undefined) {
  if (!expected || expected.length < 16 || !given) return false;
  const key = await hmacKey("compare", ["sign"]);
  const [a, b] = await Promise.all([
    crypto.subtle.sign("HMAC", key, enc.encode(expected)),
    crypto.subtle.sign("HMAC", key, enc.encode(given)),
  ]);
  return hex(a) === hex(b);
}

/** Raw request text for a route behind the ingest guard (the guard has already read it). */
export const rawBody = (c: Context): string => c.get("raw") as string;

export function createApp(deps: {
  d1: D1Like;
  env: Env;
  registry: Registry;
  version?: string;
  now?: () => Date;
}): Hono {
  const now = deps.now ?? (() => new Date());
  const version = deps.version ?? deps.env.APP_VERSION ?? "dev";
  const app = new Hono();
  const db = drizzle(deps.d1, { schema: core });

  const ingest: MiddlewareHandler = async (c, next) => {
    const raw = await c.req.raw.clone().text();
    if (!(await signatureOk(deps.env.INGEST_HMAC_KEY, c.req.header("x-signature") ?? "", raw)))
      return c.json({ error: "bad key" }, 401);
    c.set("raw", raw);
    await next();
  };
  const secret: MiddlewareHandler = async (c, next) => {
    // The live Apps Script bridge sends `x-health-key`; everything else sends `x-health-secret`. Both count.
    const given = c.req.header("x-health-secret") ?? c.req.header("x-health-key");
    if (!(await sameSecret(deps.env.HEALTH_SECRET, given))) return c.json({ error: "no" }, 401);
    await next();
  };
  // Fails closed: until sign-in installs its guard, every person route answers 401. Areas capture
  // `person` at registration, so it delegates to whatever is installed when the request arrives.
  let personImpl: MiddlewareHandler = async (c) => c.json({ error: "login_needed" }, 401);
  const person: MiddlewareHandler = (c, next) => personImpl(c, next);

  const ctx: Ctx = {
    d1: deps.d1,
    db,
    env: deps.env,
    version,
    registry: deps.registry,
    now,
    call: async (path, init) => app.request(path, init),
    guard: { ingest, secret, person },
    setPersonGuard: (guard) => {
      personImpl = guard;
    },
  };

  // Before the first request on a new version: apply pending expand-only migrations, note the deploy.
  let ready: Promise<void> | undefined;
  const boot = async () => {
    await applyPending(deps.d1, deps.registry.migrations);
    await deps.d1
      .prepare("insert or ignore into deploys (version, first_seen_at) values (?, ?)")
      .bind(version, istText(now()))
      .run();
  };
  // Every answer says which contract it speaks, so a page left open on an older one can show "updating".
  app.use("*", async (c, next) => {
    await next();
    c.res.headers.set(CONTRACT_HEADER, CONTRACT_VERSION);
  });
  app.use("*", async (c, next) => {
    ready ??= boot();
    try {
      await ready;
    } catch {
      ready = undefined;
      return c.json({ error: "updating" }, 503);
    }
    await next();
  });

  for (const area of deps.registry.areas) if (area.routes) app.route("/", area.routes(ctx));
  app.notFound((c) => c.json({ error: "not found" }, 404));
  return app;
}
