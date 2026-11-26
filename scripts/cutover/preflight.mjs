// Preflight (ticket V4): lists every missing binding, secret or var for the Pages project, and every value that is the wrong
// shape. It reads values only to judge their shape and NEVER prints one, nor an email address.
//   node scripts/cutover/preflight.mjs [--target production|preview] [--env ../.env] [--toml web/wrangler.toml] [--local]
import { people } from "../../web/lib/auth.js";

// kind: binding (d1, kv) | secret | var. `min` is the shortest length the code accepts.
export const REQUIRED = [
  { name: "DB", kind: "d1", why: "D1 database: jobs, calls, news, feedback (every /api/v2 route)" },
  { name: "SP", kind: "kv", why: "KV: sign-in links and rate limits (and the old queue until it is retired)" },
  { name: "SP_PEOPLE", kind: "secret", why: 'JSON {"owner": "<email>", "father": "<email>"}: who may sign in' },
  { name: "SP_COOKIE_KEY", kind: "secret", min: 32, why: "signs the session cookie" },
  { name: "SP_VM_KEY", kind: "secret", min: 16, why: "the VM's key for /api/vm" },
  { name: "SP_INGEST_KEY", kind: "secret", min: 16, why: "write-only key public jobs use for /api/v2/ingest" },
  { name: "GOOGLE_BRIDGE_URL", kind: "secret", why: "Apps Script bridge that emails the sign-in link" },
  { name: "GOOGLE_BRIDGE_KEY", kind: "secret", why: "key for that bridge" },
  { name: "KITE_API_KEY", kind: "secret", why: "Kite connect" },
  { name: "KITE_API_SECRET", kind: "secret", why: "Kite connect" },
  { name: "SP_OWNER", kind: "var", optional: true, why: "which SP_PEOPLE id is the owner (default owner)" },
  { name: "KITE_API_BASE", kind: "var", optional: true, why: "test override only" },
  { name: "KITE_LOGIN_BASE", kind: "var", optional: true, why: "test override only" },
];

// Shape problems for one .env value, in words that never include the value.
function shapeProblem(item, value) {
  if (item.min && value.length < item.min) return `is shorter than ${item.min} characters`;
  if (item.name === "SP_PEOPLE") {
    const set = people({ SP_PEOPLE: value });
    const missing = ["owner", "father"].filter((id) => !Object.hasOwn(set, id));
    if (missing.length) return `must be JSON with a valid email for each of: owner, father (missing or invalid: ${missing.join(", ")})`;
  }
  return null;
}

export function runPreflight({ env, toml, remote, target = "production" }) {
  const problems = [];
  const cfg = remote?.[target];
  if (!cfg) problems.push({ kind: "remote_unknown", name: "(project)", note: "could not read the Pages project's bindings and secrets from Cloudflare; only this machine was checked" });
  const tomlHas = (binding, table) => new RegExp(`\\[\\[${table}\\]\\][^\\[]*binding\\s*=\\s*"${binding}"`).test(toml || "");
  for (const item of REQUIRED) {
    if (item.kind === "d1" || item.kind === "kv") {
      const table = item.kind === "d1" ? "d1_databases" : "kv_namespaces";
      // With pages_build_output_dir in it, web/wrangler.toml is the source of truth: a deploy replaces bindings set in the dashboard.
      if (!tomlHas(item.name, table)) {
        const there = (cfg?.[item.kind] || []).includes(item.name) ? " (it is set in the dashboard, but a deploy would drop it)" : "";
        problems.push({ kind: "missing_binding", name: item.name, note: `${item.why}. Not in web/wrangler.toml${there}.` });
      }
      continue;
    }
    const value = env?.[item.name];
    const set = (cfg?.env_vars || []).includes(item.name);
    if (!item.optional) {
      if (cfg && !set) problems.push({ kind: "missing_remote", name: item.name, note: `${item.why}. Not set on the ${target} project.` });
      if (value == null || value === "") problems.push({ kind: "missing_local", name: item.name, note: `${item.why}. Not in the VM .env, so it cannot be set from there.` });
    }
    if (value) {
      const bad = shapeProblem(item, value);
      if (bad) problems.push({ kind: "bad_shape", name: item.name, note: `in .env ${bad}` });
    }
  }
  const owner = env?.SP_OWNER;
  if (owner) {
    const ids = Object.keys(people({ SP_PEOPLE: env.SP_PEOPLE }));
    if (!ids.includes(owner)) problems.push({ kind: "bad_shape", name: "SP_OWNER", note: `in .env is not one of the SP_PEOPLE ids (${ids.join(", ") || "none valid"})` });
  }
  return { ok: problems.length === 0, target, problems };
}

// The safe way to set one: the value goes from .env to wrangler's stdin, never onto a command line or into a log.
export function setCommand(name, project = "stockpilotgn", target = "production") {
  return `scripts/cutover/set-secret.sh ${name} ${project}${target === "preview" ? " preview" : ""}`;
}

const FIX = {
  missing_binding: (p) => `Add it to web/wrangler.toml (D1: [[d1_databases]] binding = "DB", database_name, database_id, migrations_dir = "migrations"); see docs/status/cutover-runbook.md step 2.`,
  missing_remote: (p, t) => `Set it: ${setCommand(p.name, "stockpilotgn", t)}`,
  missing_local: (p, t) => `Put ${p.name}=... in the VM .env first (the owner may paste it in chat; never repeat it), then ${setCommand(p.name, "stockpilotgn", t)}`,
  bad_shape: (p, t) => `Fix the value in the VM .env, then ${setCommand(p.name, "stockpilotgn", t)}`,
  remote_unknown: () => "Give wrangler a login that can read the project, or set CLOUDFLARE_API_TOKEN, and run again.",
};

export function formatReport(r) {
  if (r.ok) return `Preflight (${r.target}): every binding, secret and var is in place.`;
  const lines = [`Preflight (${r.target}): ${r.problems.length} problem${r.problems.length === 1 ? "" : "s"}, no deploy until they are fixed.`];
  for (const p of r.problems) lines.push(`- ${p.name}: ${p.note}\n    ${FIX[p.kind]?.(p, r.target) ?? ""}`);
  return lines.join("\n");
}
