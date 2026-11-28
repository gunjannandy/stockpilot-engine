// C-083-1: the og route returns an image or a placeholder.
import { expect, it } from "vitest";
import ogRoutes from "../api/src/og/routes";

const ctx = {
  guard: { person: async (_c: unknown, next: () => Promise<void>) => next() },
} as never;
const page = (img: string) =>
  new Response(`<html><head><meta property="og:image" content="${img}"></head></html>`);
const app = (fetcher: (u: string) => Promise<Response>) => ogRoutes(ctx, { fetch: fetcher });

it("C-083-1 returns the page's image, else a placeholder", async () => {
  const good = app(async (u) =>
    u.endsWith("/pic.png")
      ? new Response("PNG", { headers: { "content-type": "image/png" } })
      : page("/pic.png"),
  );
  const r = await good.request("/api/og?url=https://news.example.com/a");
  expect(r.headers.get("content-type")).toBe("image/png");

  const none = await app(async () => new Response("<html></html>")).request(
    "/api/og?url=https://news.example.com/a",
  );
  expect(none.headers.get("content-type")).toBe("image/svg+xml");

  const down = await app(async () => {
    throw new Error("x");
  }).request("/api/og?url=https://news.example.com/a");
  expect(down.headers.get("content-type")).toBe("image/svg+xml");

  let called = false;
  const blocked = await app(async () => {
    called = true;
    return page("/p");
  }).request("/api/og?url=http://127.0.0.1/admin");
  expect(blocked.headers.get("content-type")).toBe("image/svg+xml");
  expect(called).toBe(false);
});
