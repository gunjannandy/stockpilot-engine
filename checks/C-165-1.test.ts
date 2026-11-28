// C-165-1: the digest route lists newly waiting prototypes with links and is empty when none are new.
import { expect, it } from "vitest";
import { makeApp } from "../api/src/testkit";

it("C-165-1 digest lists new prototypes once", async () => {
  const t = await makeApp();
  type R = { prototypes: { id: string; link: string }[] };
  expect(((await (await t.withSecret("/api/digest/prototypes")).json()) as R).prototypes).toEqual(
    [],
  );
  await t.signed("POST", "/api/digest/prototypes", {
    id: "p1",
    title: "News screen",
    link: "https://preview.example.com/p1",
  });
  const first = (await (await t.withSecret("/api/digest/prototypes")).json()) as R;
  expect(first.prototypes.map((p) => [p.id, p.link])).toEqual([
    ["p1", "https://preview.example.com/p1"],
  ]);
  expect(((await (await t.withSecret("/api/digest/prototypes")).json()) as R).prototypes).toEqual(
    [],
  );
  expect((await t.app.request("/api/digest/prototypes")).status).toBe(401);
});
