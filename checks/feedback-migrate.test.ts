// The v2 feedback map: asks keep their ticket and status; a message with no ask comes in as Received.
import { expect, it } from "vitest";
import { FeedbackRow } from "../contract/src/feedback/feedback";
import map from "../tools/migrate/feedback";

it("v2 asks and messages become valid feedback rows", () => {
  const ask = map.tables["d1:asks"]?.map({
    id: "a1",
    original: "o",
    line_en: "l",
    status: "being_built",
    issue_number: 12,
    updated_at: "2026-11-25 09:15:00",
  }) as { row: unknown };
  const row = FeedbackRow.parse(ask.row);
  expect(row.ticket).toBe(12);
  expect(row.status).toBe("being_built");
  const msg = map.tables["d1:feedback"]?.map({
    id: "m1",
    text: "t",
    created_at: "2026-11-25T09:15:00+05:30",
  }) as { row: unknown };
  expect(FeedbackRow.parse(msg.row).status).toBe("received");
});
