// C-035-1: a new call adds a row; no row is updated.
import { readdirSync, readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { makeApp } from "../api/src/testkit";
import { callBase } from "./calls-fixture";

describe("C-035-1 calls are append-only", () => {
  it("a second write of the same call changes nothing; a new day adds a row; the screen reads the latest", async () => {
    const t = await makeApp();
    const first = (await (
      await t.signed("POST", "/api/calls/publish", { rows: [callBase()] })
    ).json()) as {
      written: number;
    };
    expect(first.written).toBe(1);
    const again = (await (
      await t.signed("POST", "/api/calls/publish", {
        rows: [callBase({ verdict: "Sell", chance: 0.2 })],
      })
    ).json()) as { written: number; ignored: number };
    expect([again.written, again.ignored]).toEqual([0, 1]);
    const stored = (await t.db
      .prepare("select verdict from calls where id = ?")
      .bind("NSE:ABC:2026-11-28:63")
      .first()) as {
      verdict: string;
    };
    expect(stored.verdict).toBe("Buy");

    const next = callBase({
      id: "NSE:ABC:2026-11-29:63",
      made_on: "2026-11-29",
      verdict: "Hold",
      chance: 0.45,
    });
    await t.signed("POST", "/api/calls/publish", { rows: [next] });
    const n = (await t.db.prepare("select count(*) as n from calls").first()) as { n: number };
    expect(n.n).toBe(2);
    const latest = (await (await t.app.request("/api/calls")).json()) as {
      as_of: string;
      calls: { verdict: string; confidence: { en: string } | null }[];
    };
    expect(latest.as_of).toBe("2026-11-29");
    expect(latest.calls.map((c) => c.verdict)).toEqual(["Hold"]);
    const hist = (await (await t.app.request("/api/calls/abc")).json()) as {
      calls: { made_on: string }[];
    };
    expect(hist.calls.map((c) => c.made_on)).toEqual(["2026-11-29", "2026-11-28"]);
  });

  it("no code in the calls folder updates or deletes a call", () => {
    for (const f of readdirSync(new URL("../api/src/calls/", import.meta.url)).filter((n) =>
      n.endsWith(".ts"),
    ))
      expect(
        readFileSync(new URL(`../api/src/calls/${f}`, import.meta.url), "utf8"),
        f,
      ).not.toMatch(/(update|delete\s+from)\s+calls\b/i);
  });

  it("refuses an unsigned write; the confidence line and compare read from the rows", async () => {
    const t = await makeApp();
    expect((await t.app.request("/api/calls/publish", { method: "POST", body: "{}" })).status).toBe(
      401,
    );
    await t.signed("POST", "/api/calls/publish", {
      rows: [
        callBase(),
        callBase({
          id: "NSE:XYZ:2026-11-28:63",
          symbol: "XYZ",
          verdict: "Hold",
          chance: 0.45,
          similar_n: 0,
          similar_beat: 0,
        }),
      ],
    });
    const cmp = (await (await t.app.request("/api/calls/compare?a=abc&b=xyz")).json()) as {
      a: { confidence: { en: string } };
      b: { confidence: unknown };
    };
    expect(cmp.a.confidence.en).toBe("Our last 24 calls like this: 15 beat the Nifty.");
    expect(cmp.b.confidence).toBeNull();
  });
});
