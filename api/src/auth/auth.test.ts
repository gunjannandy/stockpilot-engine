import { describe, expect, it } from "vitest";
import { areaNames, loadRegistry } from "../../migrate/discover";

describe("auth area", () => {
  it("is discovered before every other area, so its guard and headers reach their routes", () => {
    expect(areaNames()[0]).toBe("auth");
  });
});

describe("person guard", () => {
  it("fails closed when an area registers before auth does", async () => {
    const { createApp } = await import("../app");
    const { SqliteD1 } = await import("../../../adapters/src/core");
    const { Hono } = await import("hono");
    const early = {
      name: "aaa",
      routes: (ctx: import("../app").Ctx) =>
        new Hono().get("/api/early", ctx.guard.person, (c) => c.json({ ok: true })),
    };
    const late = (await import("./routes")).default;
    const app = createApp({
      d1: new SqliteD1(),
      env: {} as never,
      registry: {
        areas: [early, { name: "auth", routes: late }],
        migrations: (await loadRegistry()).migrations,
      },
    });
    expect((await app.request("/api/early")).status).toBe(401);
  });
  it("is closed with no sign-in area at all", async () => {
    const { createApp } = await import("../app");
    const { SqliteD1 } = await import("../../../adapters/src/core");
    const { Hono } = await import("hono");
    const only = {
      name: "x",
      routes: (ctx: import("../app").Ctx) =>
        new Hono().get("/api/x", ctx.guard.person, (c) => c.json({ ok: true })),
    };
    const app = createApp({
      d1: new SqliteD1(),
      env: {} as never,
      registry: { areas: [only], migrations: (await loadRegistry()).migrations },
    });
    expect((await app.request("/api/x")).status).toBe(401);
  });
});
