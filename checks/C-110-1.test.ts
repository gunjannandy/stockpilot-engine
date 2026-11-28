// C-110-1: unreachable health renders that line.
import { expect, it } from "vitest";
import { renderEmail } from "../api/src/email/render";

it("C-110-1 health null says it is unreachable", () => {
  const html = renderEmail({ date: "2026-11-29", news: [], health: null }, "owner");
  expect(html).toContain("Health is unreachable");
});
