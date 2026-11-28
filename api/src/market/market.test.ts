import { IndicesResponse } from "@stockpilot/contract";
import { describe, expect, it } from "vitest";
import { makeApp } from "../testkit";

describe("GET /api/market/indices", () => {
  it("is empty while no market run is published", async () => {
    const { app } = await makeApp();
    const r = await app.request("/api/market/indices");
    expect(r.status).toBe(200);
    expect(IndicesResponse.parse(await r.json())).toEqual({ as_of: null, indices: [] });
  });

  it("answers the Nifty from the newest market row, with no invented day change", async () => {
    let t = Date.parse("2026-11-26T12:00:00Z");
    const { app, db } = await makeApp({ now: () => new Date(t) });
    await app.request("/api/market/indices"); // the first request applies the migrations
    t += 3600_000; // and the pointer cache forgets its empty answer
    const rows = [
      { day: "2026-11-25", nifty_close: 100 },
      { day: "2026-11-26", nifty_close: 123.45 },
    ];
    await db
      .prepare(
        "insert into pointers (dataset, run_id, previous_run_id, as_of, published_at, rows, file, summary) values ('market','r1',null,'2026-11-26','2026-11-26T18:00:00+05:30',2,null,'{}')",
      )
      .run();
    for (const [i, r] of rows.entries())
      await db
        .prepare("insert into dataset_rows (dataset, run_id, seq, body) values ('market','r1',?,?)")
        .bind(i, JSON.stringify(r))
        .run();
    const got = IndicesResponse.parse(await (await app.request("/api/market/indices")).json());
    expect(got).toEqual({
      as_of: "2026-11-26T15:30:00+05:30",
      indices: [{ id: "nifty50", name: "Nifty 50", close: 123.45, change_pct: null }],
    });
  });

  it("is empty when the row has no close", async () => {
    let t = Date.parse("2026-11-26T12:00:00Z");
    const { app, db } = await makeApp({ now: () => new Date(t) });
    await app.request("/api/market/indices"); // the first request applies the migrations
    t += 3600_000; // and the pointer cache forgets its empty answer
    await db
      .prepare(
        "insert into pointers (dataset, run_id, previous_run_id, as_of, published_at, rows, file, summary) values ('market','r1',null,'2026-11-26','2026-11-26T18:00:00+05:30',1,null,'{}')",
      )
      .run();
    await db
      .prepare("insert into dataset_rows (dataset, run_id, seq, body) values ('market','r1',0,?)")
      .bind(JSON.stringify({ day: "2026-11-26", nifty_close: null }))
      .run();
    const got = IndicesResponse.parse(await (await app.request("/api/market/indices")).json());
    expect(got.indices).toEqual([]);
  });
});
