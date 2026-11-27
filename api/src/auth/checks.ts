// Production checks for sign-in. Nobody signs in to production by hand; these call the real routes.
import { authLinks } from "../../drizzle/auth";
import type { ProductionCheck } from "../app";
import { audienceOf, authEnv, devMode, LINK_SECONDS, newToken, people, sha256hex } from "./lib";

const checks: ProductionCheck[] = [
  {
    // C-001-2: a signed-out visit goes to sign-in, and the data door answers 401.
    id: "C-001-2",
    async run(ctx) {
      if (devMode(authEnv(ctx))) return { ok: true, detail: "sign-in is off in development" };
      const visit = await ctx.call("/", { redirect: "manual" });
      const to = visit.headers.get("location") ?? "";
      if (visit.status !== 302 || !to.startsWith("/login"))
        return {
          ok: false,
          detail: `a signed-out visit got ${visit.status}, not a redirect to sign-in`,
        };
      const api = await ctx.call("/api/me");
      if (api.status !== 401)
        return { ok: false, detail: `/api/me answered ${api.status} signed out` };
      return { ok: true, detail: "signed-out visit redirects to sign-in; /api/me answers 401" };
    },
  },
  {
    // C-006-1: strict headers on answers; the session cookie is host-only, HttpOnly, Secure and SameSite.
    // It mints a throwaway link, spends it through the real route and reads the Set-Cookie it gets back.
    id: "C-006-1",
    async run(ctx) {
      const env = authEnv(ctx);
      if (devMode(env)) return { ok: true, detail: "sign-in is off in development" };
      const who = Object.keys(people(env))[0];
      if (!who) return { ok: false, detail: "sign-in is not set up: no addresses configured" };
      const login = await ctx.call("/login");
      const h = (name: string) => login.headers.get(name) ?? "";
      if (!h("content-security-policy").includes("default-src"))
        return { ok: false, detail: "answers carry no Content-Security-Policy" };
      if (!/max-age=\d{7,}/.test(h("strict-transport-security")))
        return { ok: false, detail: "answers carry no Strict-Transport-Security" };
      const token = newToken();
      await ctx.db.insert(authLinks).values({
        hash: await sha256hex(token),
        person: who,
        next: "/",
        expiresAt: Math.floor(ctx.now().getTime() / 1000) + LINK_SECONDS,
      });
      const res = await ctx.call("/login/verify", {
        method: "POST",
        headers: { "content-type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ t: token }).toString(),
        redirect: "manual",
      });
      const cookie = res.headers.get("set-cookie") ?? "";
      const want = ["HttpOnly", "Secure", "SameSite=Lax", "Path=/", "Max-Age=31536000"];
      const lacks = want.filter((a) => !cookie.includes(a));
      if (/domain=/i.test(cookie)) lacks.push("no Domain");
      if (!cookie.startsWith(audienceOf(env) === "preview" ? "__Host-sp_preview=" : "__Host-sp="))
        lacks.push("the __Host- name");
      return lacks.length
        ? { ok: false, detail: `session cookie lacks ${lacks.join(", ")}` }
        : {
            ok: true,
            detail: "CSP and HSTS on answers; cookie is host-only, HttpOnly, Secure, SameSite",
          };
    },
  },
];
export default checks;
