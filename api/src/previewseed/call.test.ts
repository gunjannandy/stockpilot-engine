import { describe, expect, it } from "vitest";
import { callReseed } from "./call";

describe("callReseed", () => {
  it("skips without an address or key", async () => {
    expect(await callReseed({})).toMatch(/no preview address/);
    expect(await callReseed({ PREVIEW_URL: "https://p.invalid" })).toMatch(/no ingest key/);
  });
  it("posts a signed request and fails on a bad answer", async () => {
    const seen: { url: string; sig: string | null }[] = [];
    const f = (ok: boolean) =>
      (async (url: string, init: RequestInit) => {
        seen.push({ url, sig: new Headers(init.headers).get("x-signature") });
        return new Response("{}", { status: ok ? 200 : 500 });
      }) as unknown as typeof fetch;
    const env = { PREVIEW_URL: "https://p.invalid/", INGEST_HMAC_KEY: "k".repeat(40) };
    expect(await callReseed(env, f(true))).toBe("preview reseeded");
    expect(seen[0]?.url).toBe("https://p.invalid/api/previewseed/reseed");
    expect(seen[0]?.sig).toMatch(/^[0-9a-f]{64}$/);
    await expect(callReseed(env, f(false))).rejects.toThrow(/500/);
  });
});
