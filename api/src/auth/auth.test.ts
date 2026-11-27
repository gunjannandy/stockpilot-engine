import { describe, expect, it } from "vitest";
import { areaNames } from "../../migrate/discover";

describe("auth area", () => {
  it("is discovered before every other area, so its guard and headers reach their routes", () => {
    expect(areaNames()[0]).toBe("auth");
  });
});
