// C-094-1: only the owner can set review states.
import { expect, it } from "vitest";
import { FATHER, makeAuthApp, OWNER } from "../api/src/auth/testkit";

it("C-094-1 the father is refused, the owner is let through", async () => {
  const t = await makeAuthApp();
  const owner = await t.signIn(OWNER);
  const father = await t.signIn(FATHER);
  const json = { "content-type": "application/json", origin: "http://localhost" };
  const post = await t.app.request("/api/feedback", {
    method: "POST",
    headers: { ...json, cookie: (father?.cookie ?? "") as string },
    body: JSON.stringify({ text: "make the numbers bigger" }),
  });
  expect(post.status).toBe(200);
  const { id } = await post.json();
  const review = (cookie?: string) =>
    t.app.request(`/api/feedback/${id}/review`, {
      method: "POST",
      headers: { ...json, ...(cookie ? { cookie } : {}) },
      body: JSON.stringify({ understanding: "bigger text", decision: "not_planned" }),
    });
  expect((await review()).status).toBe(401);
  expect((await review(father?.cookie)).status).toBe(403);
  expect((await review(owner?.cookie)).status).toBe(200);
  const list = await t.app.request("/api/feedback", { headers: { cookie: father?.cookie ?? "" } });
  const body = await list.json();
  expect(body.person).toBe("father");
  expect(body.asks[0].status).toBe("not_planned");
  t.bridge.restore();
});
