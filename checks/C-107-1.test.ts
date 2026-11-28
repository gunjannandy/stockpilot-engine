// C-107-1 (contract): a click writes one usage count.
import { expect, it } from "vitest";
import { makeApp } from "../api/src/testkit";

it("a click writes one usage count", async () => {
  const { app, db } = await makeApp();
  const r = await app.request("/api/usage", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ screen: "admin", button: "try-again" }),
  });
  expect(r.status).toBe(200);
  const row = await db.prepare("select sum(n) as n from usage_counts").first();
  expect(row.n).toBe(1);
});
