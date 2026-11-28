// LO237: production names the preview Worker so the nightly reseed has somewhere to call.
import { readFileSync } from "node:fs";
import { expect, it } from "vitest";

it("wrangler.toml sets PREVIEW_URL to the preview Worker address", () => {
  const toml = readFileSync(new URL("../wrangler.toml", import.meta.url), "utf8");
  expect(toml).toMatch(/^PREVIEW_URL = "https:\/\/stockpilot-preview\.stockpilotgn\.workers\.dev"$/m);
});
