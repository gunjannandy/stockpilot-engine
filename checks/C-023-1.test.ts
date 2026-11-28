// C-023-1 / C-023-3: a row that changed between a dataset's previous and current run carries a
// mark, opening it clears it for both people; news without a change is the newspaper, not a mark.
import { describe, expect, it } from "vitest";
import { marksRoutes } from "../api/src/marks/routes";
import { items, publishApp, testDatasets } from "../api/src/publish/testkit";

async function setup() {
  const t = await publishApp();
  const marks = marksRoutes(
    {
      d1: t.db,
      now: () => new Date("2026-11-27T10:00:00Z"),
      guard: { person: async (_c: unknown, n: () => Promise<void>) => n() },
    } as never,
    { datasets: testDatasets },
  );
  const get = async () => (await marks.request("/api/marks")).json() as Promise<any>;
  const seen = (body: unknown) =>
    marks.request("/api/marks/seen", { method: "POST", body: JSON.stringify(body) });
  return { t, get, seen };
}

describe("C-023 change marks", () => {
  it("marks a changed or new row and clears it once seen", async () => {
    const { t, get, seen } = await setup();
    await t.rows("roomy", "a", items(3));
    await t.finish("roomy", "a");
    expect((await get()).items).toEqual([]); // nothing to compare yet
    await t.rows("roomy", "b", [
      ...items(3).map((r) => (r.id === "r1" ? { ...r, n: 99 } : r)),
      { id: "r9", n: 1 },
    ]);
    await t.finish("roomy", "b");
    const a = await get();
    expect(a.items.map((i: any) => [i.key, i.isNew, i.fields])).toEqual([
      ["r1", false, ["n"]],
      ["r9", true, []],
    ]);
    expect(a.unseen).toBe(2);
    await seen({ dataset: "roomy", key: "r1" });
    expect((await get()).unseen).toBe(1);
    await seen({ all: true });
    expect((await get()).unseen).toBe(0);
  });
});
