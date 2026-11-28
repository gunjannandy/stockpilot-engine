// GET /api/og?url=...: a link-preview image for a news card, or a placeholder. The page's og:image is fetched
// by the Worker (never the browser), only for public http(s) hosts, and only an image answer is passed on.
import { Hono } from "hono";
import type { Ctx } from "../app";

type Fetch = (url: string, init?: RequestInit) => Promise<Response>;

const PRIVATE =
  /^(localhost|.*\.local|.*\.internal|0\.0\.0\.0|127\.|10\.|192\.168\.|169\.254\.|172\.(1[6-9]|2\d|3[01])\.|\[?::1\]?$)/i;

export function publicUrl(raw: string | undefined): URL | null {
  try {
    const u = new URL(raw ?? "");
    return (u.protocol === "https:" || u.protocol === "http:") && !PRIVATE.test(u.hostname)
      ? u
      : null;
  } catch {
    return null;
  }
}

export const placeholder = (label: string): string =>
  `<svg xmlns="http://www.w3.org/2000/svg" width="600" height="315" viewBox="0 0 600 315"><rect width="600" height="315" fill="#e5e7eb"/><text x="300" y="165" text-anchor="middle" font-family="sans-serif" font-size="28" fill="#6b7280">${label.replace(/[<>&"]/g, "").slice(0, 40)}</text></svg>`;

export function ogImageUrl(html: string, base: URL): URL | null {
  const m =
    /<meta[^>]+(?:property|name)=["']og:image["'][^>]*content=["']([^"']+)["']/i.exec(html) ??
    /<meta[^>]+content=["']([^"']+)["'][^>]*(?:property|name)=["']og:image["']/i.exec(html);
  if (!m?.[1]) return null;
  try {
    return publicUrl(new URL(m[1].replace(/&amp;/g, "&"), base).href);
  } catch {
    return null;
  }
}

export default function routes(ctx: Ctx, opts: { fetch?: Fetch } = {}) {
  const app = new Hono();
  const get: Fetch = opts.fetch ?? ((u, i) => fetch(u, i));

  app.get("/api/og", ctx.guard.person, async (c) => {
    const page = publicUrl(c.req.query("url"));
    const fallback = () =>
      c.body(placeholder(page?.hostname ?? "news"), 200, {
        "content-type": "image/svg+xml",
        "cache-control": "public, max-age=3600",
      });
    if (!page) return fallback();
    try {
      const html = await get(page.href, { headers: { "user-agent": "stockpilot-preview/1.0" } });
      const img = html.ok ? ogImageUrl((await html.text()).slice(0, 200_000), page) : null;
      if (!img) return fallback();
      const res = await get(img.href);
      const type = res.headers.get("content-type") ?? "";
      if (!res.ok || !type.startsWith("image/")) return fallback();
      return c.body(await res.arrayBuffer(), 200, {
        "content-type": type,
        "cache-control": "public, max-age=86400",
      });
    } catch {
      return fallback();
    }
  });

  return app;
}
