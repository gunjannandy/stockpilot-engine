// BROWSERFIX: every queue(...) call in the page code posts a job the live contract accepts, with exactly its payload keys.
import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import "../public/buttons.js";
const B = globalThis.SPButtons;
const contract = JSON.parse(readFileSync(new URL("../../schemas/live-contract.json", import.meta.url), "utf8"));
const dir = new URL("../public/", import.meta.url);
const files = ["app.js", ...readdirSync(new URL("screens/", dir)).filter(f => f.endsWith(".js")).map(f => "screens/" + f)];
// queue("kind", { a: .., b: .. }, ...) -> [kind, [keys]] (top-level keys only; values here never hold braces except `target: t`)
const calls = [];
for (const f of files) {
  const src = readFileSync(new URL(f, dir), "utf8");
  for (const m of src.matchAll(/\bqueue\(\s*"([a-z_]+)"\s*,\s*\{([^}]*)\}/g)) {
    const keys = m[2].split(/,(?![^(]*\))/).map(s => s.trim().split(/[:\s]/)[0]).filter(Boolean);
    calls.push({ f, kind: m[1], keys });
  }
}

describe("the page's buttons", () => {
  it("are found in the page code", () => { expect(calls.length).toBeGreaterThan(15); });
  for (const { f, kind, keys } of calls) {
    it(`${kind} (${f}) posts a job the contract accepts, with exactly its payload keys`, () => {
      const p = B.plan(kind, Object.fromEntries(keys.map(k => [k, "SBIN"])));
      if (p.url === "/api/v2/feedback") return expect(Object.keys(p.body)).toEqual(["text"]);
      expect(p.url).toBe("/api/v2/jobs");
      const spec = contract.job_kinds[p.body.kind];
      expect(spec, `${p.body.kind} is not a contract kind`).toBeTruthy();
      expect(spec.runs_on).not.toBe("github_public");
      expect(Object.keys(p.body.payload).sort()).toEqual([...spec.payload].sort());
    });
  }
});
