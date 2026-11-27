// C-112-3: a failing row check holds back that row with its reason and the run publishes; past the
// threshold the run fails.
import { expect, it } from "vitest";
import { items, publishApp } from "../api/src/publish/testkit";

it("C-112-3 a bad row is held back with its reason and the run publishes", async () => {
  const t = await publishApp();
  const rows = [...items(8), { id: "bad", n: -1 }, { id: "", n: 1 }];
  const few = [...items(3), { id: "bad", n: -1 }, { id: "", n: 1 }];
  const r = (await (await t.rows("roomy", "a", rows)).json()) as {
    accepted: number;
    held_back: number;
  };
  expect(r).toEqual({ accepted: 9, held_back: 1 }); // roomy has no row check: only the empty id fails its schema
  expect((await t.finish("roomy", "a")).status).toBe(200);

  const s = await t.rows("small", "a", few);
  expect(await s.json()).toEqual({ accepted: 3, held_back: 2 });
});

it("C-112-3 held-back rows keep their reason for Admin", async () => {
  const t = await publishApp();
  await t.rows("small", "a", [...items(9), { id: "bad", n: -5 }]);
  expect((await t.finish("small", "a")).status).toBe(200);
  const held = (await (await t.app.request("/api/publish/held/small")).json()) as {
    held: { reason: string; run_id: string }[];
  };
  expect(held.held).toHaveLength(1);
  expect(held.held[0]?.reason).toBe("n is negative");
  const seen = (await (await t.read("small")).json()) as { rows: { id: string }[] };
  expect(seen.rows.map((x) => x.id)).not.toContain("bad");
});

it("C-112-3 past the threshold the run fails and the last good run stays", async () => {
  const t = await publishApp();
  await t.rows("roomy", "a", items(4));
  await t.finish("roomy", "a");
  await t.rows("roomy", "b", [...items(2), { id: "", n: 1 }, { id: "", n: 2 }]); // half held back, over the 20% limit
  const fin = await t.finish("roomy", "b");
  expect(fin.status).toBe(422);
  expect(((await fin.json()) as { reason: string }).reason).toMatch(/held back/);
  expect(((await (await t.read("roomy")).json()) as { run_id: string }).run_id).toBe("a");
});
