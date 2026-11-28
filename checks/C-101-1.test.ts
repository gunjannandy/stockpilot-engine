// C-101-1: paused releases move nothing to production (the flag promote.yml reads).
import { expect, it } from "vitest";
import { makeApp } from "../api/src/testkit";

const put = (
  app: { request: (p: string, i: RequestInit) => Response | Promise<Response> },
  p: string,
  b: unknown,
) =>
  app.request(p, {
    method: "PUT",
    body: JSON.stringify(b),
    headers: { "content-type": "application/json" },
  });

it("C-101-1 the switch sets the flag the promote step reads, and clears it", async () => {
  const { app } = await makeApp();
  const status = async () =>
    ((await (await app.request("/api/status")).json()) as { paused: boolean }).paused;
  expect(await status()).toBe(false);
  expect((await put(app, "/api/admin/release-pause", { paused: true })).status).toBe(200);
  expect(await status()).toBe(true);
  expect(
    ((await (await app.request("/api/admin/state")).json()) as { release_paused: boolean })
      .release_paused,
  ).toBe(true);
  await put(app, "/api/admin/release-pause", { paused: false });
  expect(await status()).toBe(false);
  expect((await put(app, "/api/admin/release-pause", { paused: "yes" })).status).toBe(400);
});
