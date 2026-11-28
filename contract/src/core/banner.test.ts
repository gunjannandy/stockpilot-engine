import { describe, expect, it } from "vitest";
import { bannerKey, isBannered, LIVE_SCREENS } from "./flags";

describe("banner flags", () => {
  it("starts every screen bannered except the five live ones and the owner's own", () => {
    for (const s of LIVE_SCREENS) expect(isBannered({}, s)).toBe(false);
    for (const s of ["worth", "funds", "record", "feedback", "itr", "marks"])
      expect(isBannered({}, s)).toBe(true);
    expect(isBannered({}, "admin")).toBe(false);
  });
  it("lets an explicit row win either way", () => {
    expect(isBannered({ [bannerKey("funds")]: false }, "funds")).toBe(false);
    expect(isBannered({ [bannerKey("today")]: true }, "today")).toBe(true);
  });
  it("bannering a section leaves the rest of the screen alone", () => {
    const f = { [bannerKey("today", "market")]: true };
    expect(isBannered(f, "today", "market")).toBe(true);
    expect(isBannered(f, "today", "calls")).toBe(false);
    expect(isBannered(f, "today")).toBe(false);
  });
  it("a bannered screen bannered whole hides its sections too", () => {
    expect(isBannered({}, "funds", "overlap")).toBe(true);
  });
});
