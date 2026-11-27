// C-112-1: rows of an unfinished run are never served; the pointer moves in one write.
import { expect, it } from "vitest";
import { items, publishApp } from "../api/src/publish/testkit";

it("C-112-1 an unfinished run is never served and publishing moves the pointer in one statement", async () => {
  const t = await publishApp();
  await t.rows("roomy", "a", items(2));
  // Staged, not finished: nothing is served.
  const none = (await (await t.read("roomy")).json()) as { run_id: string | null; rows: unknown[] };
  expect(none.run_id).toBeNull();
  expect(none.rows).toEqual([]);

  await t.finish("roomy", "a");
  await t.rows("roomy", "b", items(3, 100)); // second run, unfinished
  const still = (await (await t.read("roomy")).json()) as {
    run_id: string;
    rows: { id: string }[];
  };
  expect(still.run_id).toBe("a");
  expect(still.rows.map((r) => r.id)).toEqual(["r0", "r1"]);

  // Finishing runs the pointer move as a single upsert inside one batch.
  const moved: string[] = [];
  const batch = t.db.batch.bind(t.db);
  t.db.batch = async (statements: { sql?: string }[]) => {
    moved.push(...statements.map((s) => String((s as unknown as { sql: string }).sql ?? "")));
    return batch(statements as never);
  };
  await t.finish("roomy", "b");
  expect(moved.filter((s) => /into pointers/.test(s))).toHaveLength(1);
  const now = (await (await t.read("roomy")).json()) as { run_id: string; rows: unknown[] };
  expect(now.run_id).toBe("b");
  expect(now.rows).toHaveLength(3);
  // The previous run stays for change marks; a run before it is gone.
  const prev = (await (await t.app.request("/api/data/roomy?run=previous")).json()) as {
    run_id: string;
    rows: unknown[];
  };
  expect(prev.run_id).toBe("a");
  expect(prev.rows).toHaveLength(2);
});
