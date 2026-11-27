// C-112-2: a dataset over 1,000 rows publishes one file per run with only its pointer in D1; past a
// dataset's write budget the door refuses it while people's writes still land.
import { expect, it } from "vitest";
import { items, publishApp } from "../api/src/publish/testkit";

const sha = "ab".repeat(32);
const name = `big.${sha.slice(0, 12)}.json`;

it("C-112-2 a big dataset keeps only its pointer and summary in D1", async () => {
  const t = await publishApp();
  const over = await t.rows("roomy", "a", items(1001));
  expect(over.status).toBe(413);
  expect(((await over.json()) as { error: string }).error).toMatch(/file/);
  const asRows = await t.rows("big", "a", items(2));
  expect(asRows.status).toBe(422);

  const done = await t.finish("big", "a", {
    ...t.prov("big", "a"),
    file: { name, sha256: sha, rows: 5200 },
    summary: { stocks: 5200 },
  });
  expect(done.status).toBe(200);
  expect(
    ((await t.db.prepare("select count(*) as n from dataset_rows").first()) as { n: number }).n,
  ).toBe(0);
  const seen = (await (await t.read("big")).json()) as {
    file: string;
    rows: unknown[];
    summary: Record<string, unknown>;
  };
  expect(seen.file).toBe(`/data/${name}`);
  expect(seen.rows).toEqual([]);
  expect(seen.summary).toMatchObject({ rows: 5200, stocks: 5200 });

  // A file whose name does not carry its hash is refused.
  const wrong = await t.finish("big", "b", {
    ...t.prov("big", "b"),
    file: { name: "big.000000000000.json", sha256: sha, rows: 9 },
  });
  expect(wrong.status).toBe(422);
});

it("C-112-2 past its write budget the door refuses a dataset; people's writes still land", async () => {
  const t = await publishApp();
  // `tiny` may write 5 rows a day.
  expect((await t.rows("tiny", "a", items(5))).status).toBe(200);
  const refused = await t.rows("tiny", "b", items(2));
  expect(refused.status).toBe(429);
  // The refused run cannot publish.
  const fin = await t.finish("tiny", "b");
  expect(fin.status).toBe(422);
  // A person's own write (the Ping button) still lands.
  const ping = await t.app.request("/api/ping", { method: "POST" });
  expect(ping.status).toBe(200);
  expect(((await t.db.prepare("select count(*) as n from ping").first()) as { n: number }).n).toBe(
    1,
  );
});

it("C-112-2 the door keeps a share of D1's daily writes for people", async () => {
  const t = await publishApp();
  await t.read("roomy"); // applies the migrations
  const day = new Date(Date.now() + 5.5 * 3600e3).toISOString().slice(0, 10);
  await t.db
    .prepare("insert into write_budget (day, dataset, writes) values (?, 'elsewhere', 80000)")
    .bind(day)
    .run();
  expect((await t.rows("roomy", "a", items(2))).status).toBe(429);
  expect((await t.app.request("/api/ping", { method: "POST" })).status).toBe(200);
});
