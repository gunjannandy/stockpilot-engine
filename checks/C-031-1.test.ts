// C-031-1: a call's verdict is one of the seven.

import { expect, it } from "vitest";
import { CallRow, VERDICTS } from "../contract/src/index";
import { callBase } from "./calls-fixture";

it("C-031-1 the seven verdicts, and nothing else", () => {
  expect([...VERDICTS]).toEqual(["Sell", "Weak", "Hold", "Watch", "Buy", "Trim", "No view yet"]);
  for (const v of VERDICTS) expect(CallRow.safeParse(callBase({ verdict: v })).success).toBe(true);
  expect(CallRow.safeParse(callBase({ verdict: "Strong buy" })).success).toBe(false);
});
