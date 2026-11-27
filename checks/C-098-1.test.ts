// C-098-1: on fixtures in v2's shapes, migrated feedback count equals v2's.
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, it } from "vitest";
import { jsonDirSource, memorySink } from "../tools/migrate/core/io";
import { LIST } from "../tools/migrate/core/list";
import { migrate } from "../tools/migrate/core/run";
import type { AreaMap } from "../tools/migrate/core/types";

// The FEEDBACK area's own map comes with that ticket; this stands in with a straight copy.
const feedbackMap: AreaMap = {
  area: "feedback",
  tables: {
    "d1:feedback": { datasets: ["feedback"], map: (row) => ({ dataset: "feedback", row }) },
    "d1:asks": { datasets: ["asks"], map: (row) => ({ dataset: "asks", row }) },
  },
};

it("C-098-1 migrated feedback count equals v2's", async () => {
  const dir = mkdtempSync(join(tmpdir(), "mig-"));
  try {
    mkdirSync(join(dir, "d1"));
    const feedback = Array.from({ length: 37 }, (_, i) => ({
      id: `v1_${i}`,
      person: i % 3 ? "owner" : "father",
      text: `ask ${i}`,
      status: i % 2 ? "received" : "understood",
      created_at: "2026-11-01T10:00:00+05:30",
    }));
    writeFileSync(join(dir, "d1", "feedback.json"), JSON.stringify(feedback));
    writeFileSync(
      join(dir, "d1", "asks.json"),
      JSON.stringify([{ id: "a1", feedback_id: "v1_0" }]),
    );
    const sink = memorySink({ feedback: ["id"], asks: ["id"] });
    const only = LIST.filter(
      (e) => e.kind === "d1" && (e.table === "feedback" || e.table === "asks"),
    );
    const r = await migrate({ source: jsonDirSource(dir), sink, maps: [feedbackMap], list: only });
    expect(r.ok).toBe(true);
    expect(sink.rows("feedback")).toHaveLength(feedback.length);
    const t = r.tables.find((x) => x.table === "feedback");
    expect(t?.v2.rows).toBe(37);
    expect(t?.v3.feedback?.rows).toBe(37);
    expect(t?.v3.feedback?.sha).toBe(t?.v2.sha); // a straight copy keeps every row byte for byte
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
