// C-137-2: the preview reads production's public files; private tables hold only made-up rows; the
// nightly reseed restores them.
import { describe, expect, it } from "vitest";
import { z } from "zod";
import { SqliteD1 } from "../adapters/src/core";
import { publicFileUrl, publicSourceFrom, seedPreview } from "../api/src/previewseed/seed";
import { fakeRows } from "../tools/fake/generate";

const Row = z.object({
  id: z.string().min(1),
  name: z.string(),
  qty: z.number().int().min(0).max(1000),
});
const ds = (name: string, visibility?: "public" | "private") =>
  ({
    name,
    job: "ping",
    table: name,
    schedule: "x",
    freshnessHours: 24,
    checks: { row: [], run: [] },
    recomputable: false,
    writeBudget: 100,
    row: Row,
    ...(visibility ? { visibility } : {}),
  }) as never;
const datasets = {
  prices: ds("prices"),
  news: ds("news", "public"),
  holdings: ds("holdings", "private"),
} as never;

const mk = () => {
  const db = new SqliteD1();
  for (const t of ["prices", "news", "holdings"])
    db.raw.exec(`create table ${t} (id text primary key, name text, qty integer)`);
  return db;
};
const prod = [{ id: "REAL-1", name: "from production", qty: 5 }];

describe("C-137-2 preview data", () => {
  it("reads production's public file for a public dataset and made-up rows where none exists", async () => {
    const db = mk();
    const asked: string[] = [];
    const out = await seedPreview(db, {
      datasets,
      seed: 1,
      publicSource: async (n) => (asked.push(n), n === "prices" ? prod : null),
    });
    expect((await db.prepare("select id from prices").all()).results).toEqual([{ id: "REAL-1" }]);
    expect(out.find((o) => o.dataset === "prices")?.from).toBe("production");
    expect(out.find((o) => o.dataset === "news")?.from).toBe("made-up");
    expect(
      (await db.prepare("select count(*) n from news").first<{ n: number }>())?.n,
    ).toBeGreaterThan(0);
  });
  it("never asks production for a private dataset and fills it with made-up rows only", async () => {
    const db = mk();
    const asked: string[] = [];
    await seedPreview(db, {
      datasets,
      seed: 4,
      publicSource: async (n) => (asked.push(n), prod),
    });
    expect(asked).not.toContain("holdings");
    const got = (await db.prepare("select * from holdings order by id").all()).results;
    const made = fakeRows(Row, got.length, 4 + 0).map((r) => r.id);
    expect(got.length).toBeGreaterThan(0);
    expect(got.map((r) => (r as { id: string }).id)).not.toContain("REAL-1");
    expect(got.every((r) => String((r as { id: string }).id).startsWith("fake-"))).toBe(true);
    expect(made.length).toBe(got.length);
  });
  it("drops rows from production that fail the contract", async () => {
    const db = mk();
    await seedPreview(db, {
      datasets,
      seed: 2,
      publicSource: async (n) => (n === "prices" ? [{ id: "", name: 1 }] : null),
    });
    const ids = (await db.prepare("select id from prices").all()).results.map(
      (r) => (r as { id: string }).id,
    );
    expect(ids.length).toBeGreaterThan(0);
    expect(ids.every((i) => i.startsWith("fake-"))).toBe(true);
  });
  it("restores the private tables on the nightly reseed", async () => {
    const db = mk();
    const opts = { datasets, seed: 9, publicSource: async () => null };
    await seedPreview(db, opts);
    const before = (await db.prepare("select * from holdings order by id").all()).results;
    await db
      .prepare("delete from holdings where id = ?")
      .bind((before[0] as { id: string }).id)
      .run();
    await db.prepare("insert into holdings values ('stray','real?',1)").run();
    await seedPreview(db, opts);
    expect((await db.prepare("select * from holdings order by id").all()).results).toEqual(before);
  });
  it("reads production's files at /data/<dataset>.json and treats a miss as no file", async () => {
    expect(publicFileUrl("https://x.example/", "prices")).toBe(
      "https://x.example/data/prices.json",
    );
    const urls: string[] = [];
    const src = publicSourceFrom("https://x.example", async (u) => {
      urls.push(String(u));
      return String(u).includes("prices")
        ? new Response(JSON.stringify({ rows: prod }), { status: 200 })
        : new Response("no", { status: 404 });
    });
    expect(await src("prices")).toEqual(prod);
    expect(await src("news")).toBeNull();
    expect(urls).toHaveLength(2);
  });
});
