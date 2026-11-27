// C-102-1: a flagged pane is hidden until switched on.

import { describe, expect, it } from "vitest";
import { HEALTH, makeApp } from "../api/src/testkit";
import { paneVisible } from "../contract/src";

describe("C-102-1 feature flags", () => {
  it("hides a flagged pane until the owner switches the flag on", async () => {
    const { app, withSecret } = await makeApp();
    const pane = { id: "drafts", flag: "drafts" };
    const read = async () =>
      ((await (await app.request("/api/flags")).json()) as { flags: Record<string, boolean> })
        .flags;
    expect(paneVisible(pane, await read())).toBe(false);
    const on = await withSecret("/api/flags", {
      method: "POST",
      body: JSON.stringify({ key: "drafts", enabled: true }),
    });
    expect(on.status).toBe(200);
    expect(paneVisible(pane, await read())).toBe(true);
    await withSecret("/api/flags", {
      method: "POST",
      body: JSON.stringify({ key: "drafts", enabled: false }),
    });
    expect(paneVisible(pane, await read())).toBe(false);
    expect(paneVisible({ id: "plain" }, await read())).toBe(true);
  });
  it("refuses a flag write without the owner's secret", async () => {
    const { app } = await makeApp();
    const res = await app.request("/api/flags", {
      method: "POST",
      body: JSON.stringify({ key: "x", enabled: true }),
    });
    expect(res.status).toBe(401);
    expect(HEALTH.length).toBeGreaterThan(0);
  });
});
