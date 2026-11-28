// C-108-3: the email's mood comes from impact directions only; coming up is the next seven days of the calendar.
import { expect, it } from "vitest";
import { mood } from "../api/src/email/routes";

it("C-108-3 mood counts directions and ignores sector-only rows", () => {
  expect(mood([])).toBeNull();
  expect(mood([{ direction: null, sector_only: true }])).toBeNull();
  expect(mood([{ direction: "good" }, { direction: "good" }, { direction: "bad" }])).toBe(
    "Mostly good news",
  );
  expect(mood([{ direction: "bad" }, { direction: "bad" }, { direction: "good" }])).toBe(
    "Mostly bad news",
  );
  expect(mood([{ direction: "good" }, { direction: "bad" }])).toBe("Mixed news");
});
