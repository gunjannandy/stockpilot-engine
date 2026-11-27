// C-146-1: the fake-data generator's output passes the contract and seeds the preview D1.

import { describe, expect, it } from "vitest";
import { z } from "zod";
import { seedPreview } from "../api/src/previewseed/seed";
import { makeApp } from "../api/src/testkit";
import { datasets } from "../contract/src/index";
import { fakeRows } from "../tools/fake/generate";

const Wide = z.object({
  id: z.string().min(1),
  at: z.string().regex(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+05:30$/),
  day: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  qty: z.number().int().min(1).max(500),
  price: z.number().min(10).max(5000),
  active: z.boolean(),
  side: z.enum(["buy", "sell"]),
  note: z.string().nullable(),
  tag: z.string().optional(),
});

describe("C-146-1 fake-data generator", () => {
  it("makes rows that pass the schema for every kind of field", () => {
    const rows = fakeRows(Wide, 40, 7);
    expect(rows).toHaveLength(40);
    for (const r of rows) expect(Wide.safeParse(r).success).toBe(true);
    expect(new Set(rows.map((r) => r.id)).size).toBe(40);
  });
  it("is the same for the same seed and different for another", () => {
    expect(fakeRows(Wide, 5, 1)).toEqual(fakeRows(Wide, 5, 1));
    expect(fakeRows(Wide, 5, 1)).not.toEqual(fakeRows(Wide, 5, 2));
  });
  it("makes passing rows for every dataset in the registry", () => {
    for (const ds of Object.values(datasets)) {
      for (const r of fakeRows(ds.row as z.ZodObject, 10, 3))
        expect(ds.row.safeParse(r).success).toBe(true);
    }
  });
  it("seeds the preview D1 with rows that read back through the contract", async () => {
    const { app, db } = await makeApp();
    await app.request("/api/ping"); // the first request applies the migrations
    const out = await seedPreview(db, { datasets, publicSource: async () => null, seed: 11 });
    expect(out.length).toBe(Object.keys(datasets).length);
    for (const ds of Object.values(datasets)) {
      const { results } = await db.prepare(`select * from ${ds.table}`).all();
      expect(results.length).toBeGreaterThan(0);
      for (const r of results) expect(ds.row.safeParse(r).success).toBe(true);
    }
  });
});
