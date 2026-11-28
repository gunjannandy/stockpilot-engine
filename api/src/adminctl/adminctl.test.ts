import { expect, it } from "vitest";
import { makeApp } from "../testkit";

it("layout carries panes per screen and flags can be switched by a person", async () => {
  const { app } = await makeApp();
  const body = {
    rail: ["today"],
    hidden: [],
    panes: { today: { order: ["b", "a"], hidden: ["c"] } },
  };
  const h = { "content-type": "application/json" };
  expect(
    (
      await app.request("/api/admin/layout", {
        method: "PUT",
        body: JSON.stringify(body),
        headers: h,
      })
    ).status,
  ).toBe(200);
  expect(((await (await app.request("/api/layout")).json()) as { layout: unknown }).layout).toEqual(
    body,
  );
  await app.request("/api/admin/flags", {
    method: "PUT",
    body: JSON.stringify({ key: "x", enabled: true }),
    headers: h,
  });
  const s = (await (await app.request("/api/admin/state")).json()) as {
    flags: Record<string, boolean>;
    layout: unknown;
  };
  expect(s.flags.x).toBe(true);
  expect(s.layout).toEqual(body);
});
