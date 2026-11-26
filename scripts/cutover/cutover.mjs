// Cutover script (ticket V4). Deploys the Pages project to a preview or to production, checks the four hard blocks against
// the new deployment's URL (behind the sign-in gate), and on a failed production deploy rolls back to the previous deployment.
//   node scripts/cutover/cutover.mjs preflight [--target production|preview]
//   node scripts/cutover/cutover.mjs deploy --target preview [--branch cutover-preview]
//   node scripts/cutover/cutover.mjs deploy --target production
//   node scripts/cutover/cutover.mjs check <url>                  (no deploy; the four checks only)
//   node scripts/cutover/cutover.mjs prove-rollback [--branch cutover-proof]   (preview only; see docs/status/cutover-runbook.md)
// Exit 0 = pass, 1 = a hard block failed (and rollback ran for production), 3 = preflight failed (nothing deployed), 2 = usage.
// Never prints a secret, a cookie or an email address.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFile } from "node:child_process";
import { fileURLToPath } from "node:url";
import { parseDeployUrl, parseDotenv } from "./lib.mjs";
import { runPreflight, formatReport } from "./preflight.mjs";
import { checkUrl, mintCookie } from "./check.mjs";
import { createCf } from "./cf.mjs";

const PRODUCTION_BRANCH = "main";

function deployArgs({ project, branch, site = "../site" }) {
  return ["wrangler", "pages", "deploy", site, "--project-name", project, "--branch", branch, "--commit-dirty=true"];
}

async function deployAndCheck({ project, branch, site, run, check, log }) {
  const [cmd, ...args] = deployArgs({ project, branch, site });
  const done = await run(cmd, args);
  if (done.code !== 0) return { error: `wrangler exited ${done.code}: ${String(done.stderr || done.stdout).slice(-300)}` };
  const url = parseDeployUrl(done.stdout);
  if (!url) return { error: "wrangler did not print a deployment URL" };
  log(`Deployed to ${url}. Checking the four hard blocks.`);
  const res = await check(url);
  log(res.ok ? "All four hard blocks pass." : `Hard block failed: ${res.failed.join(", ")}`);
  return { url, check: res };
}

export async function runCutover({ target, branch, project, preflight, siteOk, cf, run, check, prodUrl, log, site }) {
  if (target === "preview" && (!branch || branch === PRODUCTION_BRANCH)) throw new Error(`a preview needs a branch other than the production branch (${PRODUCTION_BRANCH})`);
  const pre = await preflight();
  if (!pre.ok) { log(pre.text); return { ok: false, stage: "preflight" }; }
  if (!siteOk()) { log("The built site folder is missing or has no index.html and data/today.json. Build it first."); return { ok: false, stage: "site" }; }

  const previous = target === "production" ? await cf.currentProduction() : null;
  const r = await deployAndCheck({ project, branch: target === "production" ? PRODUCTION_BRANCH : branch, site, run, check, log });
  if (r.error) { log(r.error); return { ok: false, stage: "deploy", error: r.error, rolledBack: false }; }
  if (r.check.ok) return { ok: true, url: r.url, rolledBack: false };

  const out = { ok: false, url: r.url, failed: r.check.failed, rolledBack: false };
  if (target !== "production") { log("Preview left as it is for inspection; nothing rolled back."); return out; }
  if (!previous) { log("No previous production deployment is recorded, so there is nothing to roll back to."); return out; }
  try {
    await cf.rollback(previous);
  } catch (err) {
    out.error = `rollback failed: ${err.message}. Production is serving the bad deployment: promote ${previous} in the Cloudflare dashboard now.`;
    log(out.error);
    return out;
  }
  const after = await check(prodUrl);
  out.rolledBack = true;
  out.liveAfterRollback = after.ok;
  log(after.ok ? `Rolled back to ${previous}; the live site passes the checks.` : `Rolled back to ${previous}, but the live site still fails: ${after.failed.join(", ")}.`);
  return out;
}

// Preview analogue of a rollback (Pages can only roll back production): deploy a deliberately broken copy of the site to a
// preview branch and require the checks to catch it, then redeploy the good site to the same branch and require a pass.
export async function proveRollback({ project, branch, preflight, run, check, makeBroken, log, site }) {
  if (!branch || branch === PRODUCTION_BRANCH) throw new Error(`a preview needs a branch other than the production branch (${PRODUCTION_BRANCH})`);
  if (preflight) { const pre = await preflight(); if (!pre.ok) { log(pre.text); return { ok: false, stage: "preflight" }; } }
  const broken = await makeBroken();
  const bad = await deployAndCheck({ project, branch, site: broken, run, check, log });
  if (bad.error) return { ok: false, error: bad.error };
  if (bad.check.ok) return { ok: false, error: "the broken preview was not caught by the checks", url: bad.url };
  log(`Broken preview caught (${bad.check.failed.join(", ")}). Redeploying the known-good site to the same branch.`);
  const good = await deployAndCheck({ project, branch, site: site || "../site", run, check, log });
  if (good.error) return { ok: false, error: good.error };
  if (!good.check.ok) return { ok: false, error: `the good site failed after the redeploy: ${good.check.failed.join(", ")}`, url: good.url };
  return { ok: true, brokenUrl: bad.url, goodUrl: good.url, caught: bad.check.failed };
}

// ---- command line --------------------------------------------------------------------------------------------------

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../..");

const exec = (cmd, args, opts = {}) => new Promise((resolve) => {
  execFile(cmd, args, { cwd: path.join(root, "web"), maxBuffer: 8e6, ...opts }, (err, stdout, stderr) => resolve({ code: err ? (typeof err.code === "number" ? err.code : 1) : 0, stdout, stderr }));
});

function oauthToken() {
  for (const p of [path.join(os.homedir(), ".config/.wrangler/config/default.toml"), path.join(os.homedir(), ".wrangler/config/default.toml")]) {
    try { const m = /^oauth_token\s*=\s*"([^"]+)"/m.exec(fs.readFileSync(p, "utf8")); if (m) return m[1]; } catch { /* next */ }
  }
  return null;
}

function arg(argv, name, dflt) { const i = argv.indexOf(name); return i >= 0 ? argv[i + 1] : dflt; }

async function main(argv) {
  const [command, ...rest] = argv;
  const project = arg(rest, "--project", "stockpilotgn");
  const target = arg(rest, "--target", "production");
  const log = (l) => console.log(l);
  const envFile = path.resolve(arg(rest, "--env", path.join(root, ".env")));
  const env = fs.existsSync(envFile) ? parseDotenv(fs.readFileSync(envFile, "utf8")) : {};
  const wrangler = process.env.WRANGLER || "wrangler";
  const run = (cmd, args) => exec(cmd === "wrangler" ? wrangler : cmd, args);
  const siteDir = path.join(root, "site");
  const siteOk = () => fs.existsSync(path.join(siteDir, "index.html")) && fs.existsSync(path.join(siteDir, "data/today.json"));

  const token = process.env.CLOUDFLARE_API_TOKEN || env.CLOUDFLARE_API_TOKEN || (await (async () => { await run("wrangler", ["whoami"]); return oauthToken(); })());
  const cf = token ? createCf({ token, project, account: process.env.CLOUDFLARE_ACCOUNT_ID || env.CLOUDFLARE_ACCOUNT_ID }) : null;
  const tomlText = fs.readFileSync(path.join(root, "web/wrangler.toml"), "utf8");

  const preflight = async () => {
    let remote = null;
    if (cf) { try { const c = await cf.projectConfig(); remote = { production: c.production, preview: c.preview }; } catch (e) { log(`(could not read the project: ${e.message})`); } }
    const r = runPreflight({ env, toml: tomlText, remote, target });
    return { ...r, text: formatReport(r) };
  };
  const check = async (url) => {
    const cookie = await mintCookie(env, "owner");
    return checkUrl(url, { cookie });
  };

  if (command === "preflight") { const r = await preflight(); log(r.text); return r.ok ? 0 : 3; }
  if (command === "check") {
    const url = rest.find((a) => a.startsWith("http"));
    if (!url) { log("usage: check <url>"); return 2; }
    const r = await check(url); log(r.ok ? "All four hard blocks pass." : `Hard block failed: ${r.failed.join(", ")}`); log(JSON.stringify({ ...r.detail, pageErrors: r.detail.pageErrors, mismatches: r.detail.mismatches.slice(0, 10) })); return r.ok ? 0 : 1;
  }
  if (command === "deploy") {
    if (!["production", "preview"].includes(target)) { log("--target must be production or preview"); return 2; }
    if (rest.includes("--build")) {
      const b = await exec(path.join(root, ".venv/bin/sp"), ["--root", root, "build-site"], { cwd: root });
      if (b.code !== 0) { log(`build-site failed: ${String(b.stderr).slice(-300)}`); return 1; }
    }
    const r = await runCutover({ target, branch: arg(rest, "--branch", "cutover-preview"), project, preflight, siteOk, cf: cf || {}, run, check, prodUrl: `https://${project}.pages.dev`, log });
    log(JSON.stringify({ ok: r.ok, stage: r.stage, url: r.url, failed: r.failed, rolledBack: r.rolledBack, liveAfterRollback: r.liveAfterRollback, error: r.error }));
    return r.ok ? 0 : r.stage === "preflight" ? 3 : 1;
  }
  if (command === "prove-rollback") {
    const makeBroken = async () => {
      const dst = fs.mkdtempSync(path.join(os.tmpdir(), "sp-broken-"));
      fs.rmSync(dst, { recursive: true });
      const cp = await exec("cp", ["-al", siteDir, dst], { cwd: root });      // hardlinks: no copy of the data
      if (cp.code !== 0) throw new Error("could not copy the site folder");
      const js = path.join(dst, "app.js");
      const original = fs.readFileSync(js, "utf8");
      fs.rmSync(js);                                                           // unlink first so the hardlinked original is not touched
      fs.writeFileSync(js, `throw new Error("cutover proof: deliberate page error");\n${original}`);
      return dst;
    };
    const r = await proveRollback({ project, branch: arg(rest, "--branch", "cutover-proof"), preflight, run, check, makeBroken, log, site: siteDir });
    log(JSON.stringify(r));
    return r.ok ? 0 : 1;
  }
  log("usage: cutover.mjs preflight|deploy|check|prove-rollback  (see the header of this file)");
  return 2;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main(process.argv.slice(2)).then((c) => process.exit(c), (e) => { console.error(`cutover: ${e.message}`); process.exit(1); });
}
