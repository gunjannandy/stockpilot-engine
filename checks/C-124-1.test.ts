// C-124-1: each outside dependency has a written fallback and a check that reports; one failing never throws.
import { expect, it } from "vitest";
import { checkDeps, DEPENDENCIES } from "../api/src/deps/deps";
import { opsApp } from "../api/src/watcher/testkit";

it("C-124-1 each dependency check reports, with its fallback, even when sources fail", async () => {
  const t = await opsApp();
  const wanted = [
    "nse",
    "bse",
    "yahoo",
    "amfi",
    "google_news",
    "kite",
    "claude_usage",
    "github_actions",
    "cloudflare_limits",
  ];
  expect(DEPENDENCIES.map((d) => d.id).sort()).toEqual([...wanted].sort());
  expect(DEPENDENCIES.every((d) => d.fallback.length > 10)).toBe(true);
  const flaky = (async (url: string) => {
    if (url.includes("nseindia")) throw new Error("refused");
    return new Response("ok");
  }) as unknown as typeof fetch;
  const out = await checkDeps(t.core(), { fetch: flaky });
  expect(out).toHaveLength(wanted.length);
  expect(out.find((o) => o.dep === "nse")?.ok).toBe(false);
  expect(out.find((o) => o.dep === "bse")?.ok).toBe(true);
  const rows = (await t.db.prepare("select dep, fallback from dep_checks").all()) as {
    results: { dep: string; fallback: string }[];
  };
  expect(rows.results).toHaveLength(wanted.length);
});
