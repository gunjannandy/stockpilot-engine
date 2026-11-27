import { describe, expect, it } from "vitest";
import { datasets, JobKind, PingRow, routes } from "../index";

describe("core contract", () => {
  it("accepts a good ping row and rejects one that is not IST", () => {
    expect(
      PingRow.safeParse({ id: "a", at: "2026-11-27T10:00:00+05:30", source: "job" }).success,
    ).toBe(true);
    expect(PingRow.safeParse({ id: "a", at: "2026-11-27T10:00:00Z", source: "job" }).success).toBe(
      false,
    );
  });
  it("registers the ping dataset with a write budget and a producing job", () => {
    expect(datasets.ping.writeBudget).toBeGreaterThan(0);
    expect(JobKind.safeParse(datasets.ping.job).success).toBe(true);
  });
  it("drops the job kinds decisions drop", () => {
    for (const gone of ["weekly_review", "feedback_read", "watchlist_add"])
      expect(JobKind.safeParse(gone).success).toBe(false);
  });
  it("lists the door routes", () => {
    expect(Object.keys(routes)).toEqual(
      expect.arrayContaining([
        "ingest_write",
        "job_start",
        "job_finish",
        "market_status",
        "heartbeat_write",
      ]),
    );
  });
});
