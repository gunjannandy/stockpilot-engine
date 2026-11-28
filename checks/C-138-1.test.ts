// C-138-1: the migration runner refuses a drop in an expand step.
import { describe, expect, it } from "vitest";
import { SqliteD1 } from "../adapters/src/core";
import { applyPending, isExpandOnly } from "../api/migrate/run";

describe("C-138-1 expand-only migrations", () => {
  it("flags every way of dropping or renaming", () => {
    for (const sql of [
      "drop table ping;",
      "DROP INDEX x;",
      "alter table ping drop column at;",
      "alter table ping rename to p2;",
      "alter table ping rename column at to t;",
      "delete from ping;",
      "-- harmless comment\n create table a(x); /* c */ drop table a;",
    ])
      expect(isExpandOnly(sql), sql).toBe(false);
  });
  it("lets additive steps through, even when a comment says drop", () => {
    expect(isExpandOnly("-- drop later, in the contract step\ncreate table a (x text);")).toBe(true);
    expect(isExpandOnly("alter table a add column y text;")).toBe(true);
  });
  it("refuses to apply an expand step with a drop and changes nothing", async () => {
    const db = new SqliteD1();
    await expect(
      applyPending(db, [
        { name: "20260101000000_ok.sql", sql: "create table a (x text);" },
        { name: "20260101000100_bad.sql", sql: "drop table a;" },
      ]),
    ).rejects.toThrow(/drop|expand/i);
    const tables = await db.prepare("select name from sqlite_master where name = 'a'").all();
    expect(tables.results).toEqual([]);
  });
  it("applies a contract step only with a fresh backup", async () => {
    const db = new SqliteD1();
    await applyPending(db, [{ name: "20260101000000_a.sql", sql: "create table a (x text);" }]);
    const step = { name: "20260102000000_drop_a.contract.sql", sql: "drop table a;" };
    await expect(applyPending(db, [step], { contract: true })).rejects.toThrow(/backup/i);
    await applyPending(db, [step], { contract: true, backupAt: new Date() });
    const gone = await db.prepare("select name from sqlite_master where name = 'a'").all();
    expect(gone.results).toEqual([]);
  });
});
