// C-106-1: a browser error posts one row to /api/errors.
import { describe, expect, it } from "vitest";
import { makeApp } from "../api/src/testkit";

const post = (
  app: { request: (p: string, i: RequestInit) => Response | Promise<Response> },
  b: unknown,
) =>
  app.request("/api/errors", {
    method: "POST",
    body: JSON.stringify(b),
    headers: { "content-type": "application/json" },
  });

describe("C-106-1 browser errors", () => {
  it("stores one row per report, without the query string", async () => {
    const { app, db } = await makeApp();
    const res = await post(app, {
      message: "x is undefined",
      pane: "ping",
      url: "/ping?secret=1",
      version: "v1",
    });
    expect(res.status).toBe(200);
    const rows = (await db.prepare("select * from browser_errors").all()) as {
      results: { message: string; pane: string; url: string }[];
    };
    expect(rows.results).toHaveLength(1);
    expect(rows.results[0]).toMatchObject({
      message: "x is undefined",
      pane: "ping",
      url: "/ping",
    });
  });
  it("refuses a report with no message", async () => {
    const { app, db } = await makeApp();
    expect((await post(app, { stack: "s" })).status).toBe(400);
    const rows = (await db.prepare("select * from browser_errors").all()) as { results: unknown[] };
    expect(rows.results).toHaveLength(0);
  });
});
