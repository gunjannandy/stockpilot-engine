// Sign-in: email link, one-year host-only cookie, strict headers, owner-only guard (stories 1 to 6).
//
// This area is discovered first by name (`auth` sorts before every other area), so the headers it sets
// reach every route registered after it. The person guard does not depend on that order: it fails
// closed until `ctx.setPersonGuard` installs this one, and areas hold a stable delegating guard.
import { eq } from "drizzle-orm";
import { Hono, type MiddlewareHandler } from "hono";
import { authLimits, authLinks } from "../../drizzle/auth";
import { type Ctx, istText } from "../app";
import {
  ADDRESS_LIMIT,
  ADDRESS_WINDOW_SECONDS,
  authEnv,
  clearedCookie,
  cookieKey,
  cookieName,
  devMode,
  IP_LIMIT,
  IP_WINDOW_SECONDS,
  knownPerson,
  LINK_SECONDS,
  newToken,
  ownerOnly,
  people,
  personForEmail,
  readCookie,
  safeNext,
  sessionCookie,
  sessionPerson,
  sha256hex,
  signSession,
  TOKEN,
} from "./lib";
import { sendLink } from "./mail";
import { confirmPage, expiredPage, loginPage, sentPage } from "./pages";

const MAX_EMAIL = 254;
const SAFE = new Set(["GET", "HEAD", "OPTIONS"]);

export const SECURITY_HEADERS: Record<string, string> = {
  "Content-Security-Policy":
    "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
  "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
  "Referrer-Policy": "same-origin",
};

const html = (body: string, status = 200, extra: Record<string, string> = {}) =>
  new Response(body, {
    status,
    headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store", ...extra },
  });

export default function routes(ctx: Ctx) {
  const env = authEnv(ctx);
  const app = new Hono();
  const nowSec = () => Math.floor(ctx.now().getTime() / 1000);

  // Every route after this one needs a signed-in person; this replaces the closed default in app.ts.
  const person: MiddlewareHandler = async (c, next) => {
    if (devMode(env)) return next();
    const who = await sessionPerson(ctx, c.req.raw);
    if (!who) return c.json({ error: "login_needed" }, 401);
    c.set("person", who);
    await next();
  };
  ctx.setPersonGuard(person);

  // Strict headers on every answer; a cookie-carrying write must come from this site.
  app.use("*", async (c, next) => {
    if (!SAFE.has(c.req.method) && readCookie(c.req.raw, cookieName(env))) {
      const origin = c.req.header("Origin");
      const same =
        origin !== undefined && origin !== "null"
          ? origin === new URL(c.req.url).origin
          : c.req.header("Sec-Fetch-Site") === "same-origin";
      if (!same) return c.json({ error: "cross_site" }, 403);
    }
    await next();
    // A response from the asset binding is immutable: rebuild it before adding headers.
    c.res = new Response(c.res.body, c.res);
    for (const [k, v] of Object.entries(SECURITY_HEADERS)) c.res.headers.set(k, v);
  });

  /** Counts one hit; false once the window's limit is passed. One D1 upsert, so it also holds across isolates. */
  async function hit(key: string, limit: number, windowSeconds: number): Promise<boolean> {
    const now = nowSec();
    await ctx.d1
      .prepare(
        "insert into auth_limits (key, n, until) values (?, 1, ?) on conflict(key) do update set " +
          "n = case when until <= ? then 1 else n + 1 end, until = case when until <= ? then ? else until end",
      )
      .bind(key, now + windowSeconds, now, now, now + windowSeconds)
      .run();
    const [row] = await ctx.db.select().from(authLimits).where(eq(authLimits.key, key));
    return (row?.n ?? 0) <= limit;
  }

  async function readFields(c: { req: { raw: Request } }) {
    const req = c.req.raw.clone();
    try {
      if ((req.headers.get("Content-Type") ?? "").includes("json")) {
        const b = (await req.json()) as { email?: unknown; next?: unknown; t?: unknown };
        return { email: b.email, next: b.next, t: b.t };
      }
      const f = await req.formData();
      return { email: f.get("email"), next: f.get("next"), t: f.get("t") };
    } catch {
      return {} as { email?: unknown; next?: unknown; t?: unknown };
    }
  }

  const ready = () =>
    cookieKey(env) !== null &&
    Object.keys(people(env)).length > 0 &&
    !!env.GOOGLE_BRIDGE_URL &&
    !!env.GOOGLE_BRIDGE_KEY;

  app.get("/login", async (c) => {
    const next = safeNext(c.req.query("next"));
    if (await sessionPerson(ctx, c.req.raw)) return c.redirect(next, 303);
    return html(loginPage({ next }));
  });

  async function issueLink(who: string, to: string, next: string, base: string) {
    const token = newToken();
    const hash = await sha256hex(token);
    try {
      await ctx.db
        .insert(authLinks)
        .values({ hash, person: who, next, expiresAt: nowSec() + LINK_SECONDS });
      if (!(await sendLink(env, to, token, base)))
        throw new Error("the send endpoint did not send the email");
    } catch (err) {
      console.error("sign-in link not sent:", err instanceof Error ? err.message : "error");
      await ctx.db
        .delete(authLinks)
        .where(eq(authLinks.hash, hash))
        .catch(() => undefined);
    }
  }

  app.post("/login", async (c) => {
    if (!ready()) return html(loginPage({ message: "Sign-in is not set up yet." }), 503);
    const fields = await readFields(c);
    const next = safeNext(fields.next);
    const email = (typeof fields.email === "string" ? fields.email : "").trim().toLowerCase();
    const wellFormed = email.length > 0 && email.length <= MAX_EMAIL && email.includes("@");

    // Every address is counted, known or not, with the same work, so limits and timing tell nothing.
    const ip = c.req.header("CF-Connecting-IP") ?? "unknown";
    const ipOk = await hit(`rl:ip:${ip}`, IP_LIMIT, IP_WINDOW_SECONDS);
    if (!ipOk)
      return html(loginPage({ next, message: "Too many tries. Wait a minute." }), 429, {
        "Retry-After": String(IP_WINDOW_SECONDS),
      });
    const addrOk = await hit(
      `rl:addr:${await sha256hex(email.slice(0, MAX_EMAIL + 1))}`,
      ADDRESS_LIMIT,
      ADDRESS_WINDOW_SECONDS,
    );
    const who = wellFormed ? await personForEmail(env, email) : null;
    if (who && addrOk) {
      const work = issueLink(who, people(env)[who] as string, next, new URL(c.req.url).origin);
      try {
        c.executionCtx.waitUntil(work);
      } catch {
        await work;
      }
    }
    return html(sentPage());
  });

  const linkFor = async (token: unknown) => {
    if (typeof token !== "string" || !TOKEN.test(token)) return null;
    const hash = await sha256hex(token);
    const [row] = await ctx.db.select().from(authLinks).where(eq(authLinks.hash, hash));
    return row && row.expiresAt > nowSec() ? row : null;
  };

  // The emailed link lands here. GET only shows a button and never spends the link (mail scanners open links).
  app.get("/login/verify", async (c) => {
    const token = c.req.query("t");
    const link = await linkFor(token);
    if (!link || !knownPerson(env, link.person)) return html(expiredPage());
    return html(confirmPage(token as string));
  });

  app.post("/login/verify", async (c) => {
    if (cookieKey(env) === null)
      return html(loginPage({ message: "Sign-in is not set up yet." }), 503);
    const { t } = await readFields(c);
    const link = await linkFor(t);
    if (!link) return html(expiredPage(), 400);
    await ctx.db.delete(authLinks).where(eq(authLinks.hash, link.hash)); // single use, even if the person left
    if (!knownPerson(env, link.person)) return html(expiredPage(), 400);
    const value = await signSession(env, link.person, ctx.now().getTime());
    return new Response(null, {
      status: 303,
      headers: {
        Location: safeNext(link.next),
        "Cache-Control": "no-store",
        "Set-Cookie": sessionCookie(env, value),
      },
    });
  });

  app.post("/logout", (c) => {
    c.header("Set-Cookie", clearedCookie(env));
    c.header("Cache-Control", "no-store");
    return c.redirect("/login", 303);
  });

  app.get("/api/me", person, (c) =>
    c.json({ person: (c as unknown as { get(k: string): string }).get("person") }),
  );
  // A write only the owner may make; later areas use `ownerOnly(ctx)` the same way.
  app.post("/api/me/owner-probe", ownerOnly(ctx), (c) =>
    c.json({ ok: true, at: istText(ctx.now()) }),
  );

  // Every other page needs a signed-in person; signed out goes to sign-in. Signed in gets the web build.
  app.all("*", async (c, next) => {
    const path = new URL(c.req.url).pathname;
    if (devMode(env) || path.startsWith("/api/") || path === "/login" || path.startsWith("/login/"))
      return next();
    if (!(await sessionPerson(ctx, c.req.raw))) {
      const here = path + new URL(c.req.url).search;
      return c.redirect(here === "/" ? "/login" : `/login?next=${encodeURIComponent(here)}`, 302);
    }
    return env.ASSETS ? env.ASSETS.fetch(c.req.raw) : next();
  });

  return app;
}
