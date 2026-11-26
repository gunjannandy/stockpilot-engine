// V4PREP: cutover tooling (scripts/cutover). Everything external (wrangler, Cloudflare API, browser) is injected, so these run offline.
import test from "node:test";
import assert from "node:assert/strict";
import { parseDotenv, parseDeployUrl, px, inr, pct, compareToday, verdict } from "../../scripts/cutover/lib.mjs";
import { runPreflight, REQUIRED, formatReport, setCommand } from "../../scripts/cutover/preflight.mjs";
import { runCutover, proveRollback } from "../../scripts/cutover/cutover.mjs";
import { verifySession } from "../lib/auth.js";
import { mintCookie } from "../../scripts/cutover/check.mjs";

const SECRET = "SENTINEL-do-not-print-0123456789abcdef0123456789";
const goodEnv = {
  SP_PEOPLE: JSON.stringify({ owner: "o@example.com", father: "f@example.com" }),
  SP_COOKIE_KEY: SECRET + "-cookie-cookie",
  SP_VM_KEY: SECRET + "-vm",
  SP_INGEST_KEY: SECRET + "-ingest",
  GOOGLE_BRIDGE_URL: "https://script.example.com/x",
  GOOGLE_BRIDGE_KEY: SECRET + "-bridge",
  KITE_API_KEY: "kitekey", KITE_API_SECRET: SECRET + "-kite",
};
const toml = `name="stockpilotgn"\n[[kv_namespaces]]\nbinding = "SP"\nid = "x"\n[[d1_databases]]\nbinding = "DB"\ndatabase_name = "sp"\ndatabase_id = "y"\n`;
const remote = (names, extra = {}) => ({ production: { env_vars: names, d1: ["DB"], kv: ["SP"] }, preview: { env_vars: names, d1: ["DB"], kv: ["SP"] }, ...extra });

test("parseDotenv reads KEY=VALUE, quotes and comments", () => {
  const m = parseDotenv(`# c\nA=1\nB="two words"\nexport C='x=y'\n\nbad line\n`);
  assert.deepEqual(m, { A: "1", B: "two words", C: "x=y" });
});

test("parseDeployUrl takes the deployment URL from wrangler output", () => {
  const out = "Uploading... (12/12)\n✨ Deployment complete! Take a peek over at https://ab12cd34.stockpilotgn.pages.dev\n";
  assert.equal(parseDeployUrl(out), "https://ab12cd34.stockpilotgn.pages.dev");
  assert.equal(parseDeployUrl("nothing here"), null);
});

test("preflight passes when every name is set remotely and in .env", () => {
  const r = runPreflight({ env: goodEnv, toml, remote: remote(Object.keys(goodEnv)), target: "production" });
  assert.equal(r.ok, true, JSON.stringify(r.problems));
});

test("preflight lists every missing binding, secret and bad value, never a value", () => {
  const env = { ...goodEnv, SP_INGEST_KEY: "x9q7zz", SP_PEOPLE: JSON.stringify({ owner: "o@example.com", dad: "d@example.com" }), SP_OWNER: "owner" };
  delete env.SP_VM_KEY;
  const names = Object.keys(goodEnv).filter((k) => k !== "SP_COOKIE_KEY");
  const r = runPreflight({ env, toml: `name="stockpilotgn"`, remote: { production: { env_vars: names, d1: [], kv: [] }, preview: { env_vars: [], d1: [], kv: [] } }, target: "production" });
  assert.equal(r.ok, false);
  const text = formatReport(r);
  for (const want of ["DB", "SP_COOKIE_KEY", "SP_VM_KEY", "SP_INGEST_KEY", "father", "web/wrangler.toml"]) assert.match(text, new RegExp(want), want);
  assert.ok(!text.includes(SECRET) && !text.includes("o@example.com") && !text.includes("x9q7zz"), "a value was printed");
});

test("preflight: SP_OWNER must be one of the SP_PEOPLE ids", () => {
  const r = runPreflight({ env: { ...goodEnv, SP_OWNER: "nobody" }, toml, remote: remote([...Object.keys(goodEnv), "SP_OWNER"]), target: "production" });
  assert.equal(r.ok, false);
  assert.ok(r.problems.some((p) => p.name === "SP_OWNER"));
});

test("preflight without a remote answer says so instead of passing", () => {
  const r = runPreflight({ env: goodEnv, toml, remote: null, target: "production" });
  assert.equal(r.ok, false);
  assert.ok(r.problems.some((p) => p.kind === "remote_unknown"));
});

test("preflight checks the preview config when the target is preview", () => {
  const r = runPreflight({ env: goodEnv, toml, remote: { production: remote(Object.keys(goodEnv)).production, preview: { env_vars: [], d1: ["DB"], kv: ["SP"] } }, target: "preview" });
  assert.equal(r.ok, false);
  assert.ok(r.problems.some((p) => p.name === "SP_PEOPLE"));
});

test("REQUIRED covers the names the code reads", () => {
  const names = REQUIRED.map((x) => x.name);
  for (const n of ["DB", "SP", "SP_PEOPLE", "SP_COOKIE_KEY", "SP_VM_KEY", "SP_INGEST_KEY", "GOOGLE_BRIDGE_URL", "GOOGLE_BRIDGE_KEY", "KITE_API_KEY", "KITE_API_SECRET"]) assert.ok(names.includes(n), n);
});

test("setCommand pipes the .env value to wrangler on stdin, never on the command line", () => {
  const c = setCommand("SP_INGEST_KEY", "stockpilotgn");
  assert.match(c, /scripts\/cutover\/set-secret\.sh SP_INGEST_KEY/);
  assert.ok(!/=/.test(c));
});

const today = { buy: [{ symbol: "AAA", entry: 250.5, target: 300, probability: 0.7 }], sell: [{ symbol: "BBB", entry: 1234.4, quantity: 10, probability: 0.33 }], keep: [] };

test("compareToday: matching rows pass; a wrong number and a missing row are named", () => {
  const rows = [{ sym: "AAA", text: `Buy AAA 70% chance target ${px(300)}` }, { sym: "BBB", text: `Weak BBB 33% chance worth ${inr(12344)}` }];
  assert.deepEqual(compareToday(rows, today).mismatches, []);
  const bad = compareToday([{ sym: "AAA", text: "Buy AAA 71% chance target ₹999" }], today);
  assert.equal(bad.mismatches.length, 3);
  assert.match(bad.mismatches.join(" "), /AAA: chance/);
  assert.match(bad.mismatches.join(" "), /AAA: target price/);
  assert.match(bad.mismatches.join(" "), /BBB.*not on screen/);
});

test("px, inr and pct match the page's own formatting", () => {
  assert.equal(px(250.5), "₹250.5");
  assert.equal(px(50), "₹50.00");
  assert.equal(px(123456), "₹1,23,456");
  assert.equal(px(null), "–");
  assert.equal(pct(0.676), "68%");
});

test("verdict: the four hard blocks, each named when it fails", () => {
  const ok = { loaded: true, gate: false, pageErrors: [], rows: 2, expectedRows: 2, nothingLine: false, mismatches: [] };
  assert.deepEqual(verdict(ok), { ok: true, failed: [] });
  assert.deepEqual(verdict({ ...ok, loaded: false }).failed, ["page_loads"]);
  assert.deepEqual(verdict({ ...ok, gate: true, loaded: false }).failed, ["page_loads"]);
  assert.deepEqual(verdict({ ...ok, pageErrors: ["boom"] }).failed, ["js_page_error"]);
  assert.deepEqual(verdict({ ...ok, rows: 0 }).failed, ["today_not_empty"]);
  assert.deepEqual(verdict({ ...ok, rows: 0, expectedRows: 0, nothingLine: true }), { ok: true, failed: [] });
  assert.deepEqual(verdict({ ...ok, rows: 0, expectedRows: 0, nothingLine: false }).failed, ["today_not_empty"]);
  assert.deepEqual(verdict({ ...ok, mismatches: ["x"] }).failed, ["numbers_match"]);
});

test("mintCookie signs a real session for the owner with SP_COOKIE_KEY", async () => {
  const c = await mintCookie({ SP_COOKIE_KEY: goodEnv.SP_COOKIE_KEY }, "owner");
  assert.equal(await verifySession(c.value, goodEnv.SP_COOKIE_KEY), "owner");
  assert.equal(c.name, "sp_session");
  await assert.rejects(mintCookie({ SP_COOKIE_KEY: "short" }, "owner"));
});

// ---- the deploy script ------------------------------------------------------------------------------------------

function world({ checks = [], prod = "prev-1", deployOut = "Deployment complete! https://aaa111.stockpilotgn.pages.dev", preflightOk = true } = {}) {
  const calls = [];
  const queue = [...checks];
  return {
    calls,
    deps: {
      log: (l) => calls.push(["log", l]),
      preflight: async () => ({ ok: preflightOk, problems: preflightOk ? [] : [{ kind: "missing", name: "DB" }], text: preflightOk ? "ok" : "missing DB" }),
      siteOk: () => true,
      cf: {
        currentProduction: async () => prod,
        rollback: async (id) => { calls.push(["rollback", id]); },
      },
      run: async (cmd, args) => { calls.push(["run", cmd, ...args]); return { code: 0, stdout: deployOut, stderr: "" }; },
      check: async (url) => { calls.push(["check", url]); return queue.shift() ?? { ok: true, failed: [] }; },
      prodUrl: "https://stockpilotgn.pages.dev",
    },
  };
}

test("production deploy: preflight, deploy, check pass, no rollback", async () => {
  const w = world();
  const r = await runCutover({ target: "production", project: "stockpilotgn", ...w.deps });
  assert.equal(r.ok, true);
  assert.ok(!w.calls.some((c) => c[0] === "rollback"));
  const dep = w.calls.find((c) => c[0] === "run");
  assert.deepEqual(dep.slice(1, 5), ["wrangler", "pages", "deploy", "../site"]);
  assert.ok(dep.includes("--branch") && dep[dep.indexOf("--branch") + 1] === "main");
});

test("a failed hard block rolls production back to the previous deployment", async () => {
  const w = world({ checks: [{ ok: false, failed: ["js_page_error"] }, { ok: true, failed: [] }] });
  const r = await runCutover({ target: "production", project: "stockpilotgn", ...w.deps });
  assert.equal(r.ok, false);
  assert.equal(r.rolledBack, true);
  assert.deepEqual(w.calls.find((c) => c[0] === "rollback"), ["rollback", "prev-1"]);
  assert.ok(w.calls.filter((c) => c[0] === "check").length === 2, "checks the live URL again after rollback");
  assert.deepEqual(r.failed, ["js_page_error"]);
});

test("rollback that itself fails is reported loudly", async () => {
  const w = world({ checks: [{ ok: false, failed: ["page_loads"] }] });
  w.deps.cf.rollback = async () => { throw new Error("api said no"); };
  const r = await runCutover({ target: "production", project: "stockpilotgn", ...w.deps });
  assert.equal(r.ok, false);
  assert.equal(r.rolledBack, false);
  assert.match(r.error, /rollback failed/i);
});

test("no previous production deployment: failure is reported, no rollback attempted", async () => {
  const w = world({ prod: null, checks: [{ ok: false, failed: ["page_loads"] }] });
  const r = await runCutover({ target: "production", project: "stockpilotgn", ...w.deps });
  assert.equal(r.rolledBack, false);
  assert.ok(!w.calls.some((c) => c[0] === "rollback"));
});

test("preflight failure stops before any deploy", async () => {
  const w = world({ preflightOk: false });
  const r = await runCutover({ target: "production", project: "stockpilotgn", ...w.deps });
  assert.equal(r.ok, false);
  assert.ok(!w.calls.some((c) => c[0] === "run"));
});

test("preview deploy uses a non-production branch and never rolls back via the API", async () => {
  const w = world({ checks: [{ ok: false, failed: ["numbers_match"] }] });
  const r = await runCutover({ target: "preview", branch: "cutover-preview", project: "stockpilotgn", ...w.deps });
  assert.equal(r.ok, false);
  assert.equal(r.rolledBack, false);
  assert.ok(!w.calls.some((c) => c[0] === "rollback"));
  const dep = w.calls.find((c) => c[0] === "run");
  assert.equal(dep[dep.indexOf("--branch") + 1], "cutover-preview");
});

test("preview branch may not be main", async () => {
  const w = world();
  await assert.rejects(runCutover({ target: "preview", branch: "main", project: "stockpilotgn", ...w.deps }), /production branch/);
});

test("proveRollback: broken preview is caught, good redeploy passes", async () => {
  const w = world({ checks: [{ ok: false, failed: ["js_page_error"] }, { ok: true, failed: [] }] });
  w.deps.makeBroken = async () => "/tmp/broken-site";
  const r = await proveRollback({ project: "stockpilotgn", branch: "cutover-proof", ...w.deps });
  assert.equal(r.ok, true);
  const deploys = w.calls.filter((c) => c[0] === "run");
  assert.equal(deploys.length, 2);
  assert.ok(deploys[0].includes("/tmp/broken-site"));
  assert.ok(deploys[1].includes("../site"));
});

test("proveRollback fails when the broken site is NOT caught", async () => {
  const w = world({ checks: [{ ok: true, failed: [] }, { ok: true, failed: [] }] });
  w.deps.makeBroken = async () => "/tmp/broken-site";
  const r = await proveRollback({ project: "stockpilotgn", branch: "cutover-proof", ...w.deps });
  assert.equal(r.ok, false);
  assert.match(r.error, /not caught/i);
});

test("set-secret.sh sends the .env value to wrangler on stdin only and prints nothing secret", async () => {
  const { execFileSync } = await import("node:child_process");
  const fs = await import("node:fs"), os = await import("node:os"), path = await import("node:path");
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "setsecret-"));
  fs.writeFileSync(path.join(dir, ".env"), `OTHER=1\nSP_INGEST_KEY="${SECRET}"\n`);
  fs.writeFileSync(path.join(dir, "fakewr"), `#!/bin/sh\necho "$@" > "${dir}/argv"\ncat > "${dir}/stdin"\n`, { mode: 0o755 });
  const out = execFileSync("bash", [path.resolve("../scripts/cutover/set-secret.sh"), "SP_INGEST_KEY", "stockpilotgn", "production"], { env: { ...process.env, SP_ENV_FILE: path.join(dir, ".env"), WRANGLER: path.join(dir, "fakewr") }, encoding: "utf8" });
  assert.equal(fs.readFileSync(path.join(dir, "stdin"), "utf8"), SECRET);
  assert.ok(!fs.readFileSync(path.join(dir, "argv"), "utf8").includes(SECRET));
  assert.ok(!out.includes(SECRET));
  assert.match(fs.readFileSync(path.join(dir, "argv"), "utf8"), /pages secret put SP_INGEST_KEY --project-name stockpilotgn --env production/);
  assert.throws(() => execFileSync("bash", [path.resolve("../scripts/cutover/set-secret.sh"), "NOPE"], { env: { ...process.env, SP_ENV_FILE: path.join(dir, ".env"), WRANGLER: path.join(dir, "fakewr") }, stdio: "pipe" }));
});

test("preflight: a D1 binding that exists only in the dashboard is a problem, because a deploy drops it", () => {
  const r = runPreflight({ env: goodEnv, toml: "name=\"stockpilotgn\"", remote: remote(Object.keys(goodEnv)), target: "production" });
  const p = r.problems.find((x) => x.name === "DB");
  assert.ok(p && /deploy would drop it/.test(p.note));
});

test("preview fixes name the preview environment", () => {
  const r = runPreflight({ env: goodEnv, toml, remote: { production: remote(Object.keys(goodEnv)).production, preview: { env_vars: [], d1: [], kv: [] } }, target: "preview" });
  assert.match(formatReport(r), /set-secret\.sh SP_PEOPLE stockpilotgn preview/);
});

test("the repo's own web/wrangler.toml declares the DB and SP bindings", async () => {
  const fs = await import("node:fs");
  const r = runPreflight({ env: goodEnv, toml: fs.readFileSync("wrangler.toml", "utf8"), remote: remote(Object.keys(goodEnv)), target: "production" });
  assert.deepEqual(r.problems, []);
});

const legacyEnv = (() => { const e = { ...goodEnv, SP_OWNER: "legacy_a" }; delete e.SP_PEOPLE; return e; })();

test("preflight: SP_PEOPLE only on the remote project is fine when SP_OWNER is in .env and set remotely", () => {
  const names = [...Object.keys(goodEnv), "SP_OWNER"];
  const r = runPreflight({ env: legacyEnv, toml, remote: remote(names), target: "production" });
  assert.equal(r.ok, true, JSON.stringify(r.problems));
});

test("preflight: SP_OWNER must reach the project as a secret when SP_PEOPLE is not in .env", () => {
  const r = runPreflight({ env: legacyEnv, toml, remote: remote(Object.keys(goodEnv)), target: "production" });
  assert.equal(r.ok, false);
  assert.ok(r.problems.some((p) => p.name === "SP_OWNER" && p.kind === "missing_remote"));
});

test("preflight: SP_OWNER set remotely only (not in .env) also passes without a local SP_PEOPLE", () => {
  const env = { ...goodEnv }; delete env.SP_PEOPLE;
  const r = runPreflight({ env, toml, remote: remote([...Object.keys(goodEnv), "SP_OWNER"]), target: "production" });
  assert.equal(r.ok, true, JSON.stringify(r.problems));
});

test("preflight: no SP_PEOPLE in .env and no SP_OWNER anywhere is still a problem", () => {
  const env = { ...goodEnv }; delete env.SP_PEOPLE;
  const r = runPreflight({ env, toml, remote: remote(Object.keys(goodEnv)), target: "production" });
  assert.equal(r.ok, false);
  assert.ok(r.problems.some((p) => p.name === "SP_OWNER"));
});
