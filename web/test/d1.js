// A local D1 for tests: node:sqlite with the real migrations and the T0 fixture rows.
// Same calls the Workers D1 binding has (prepare, bind, first, all, run, batch), so route code runs unchanged.
import { DatabaseSync } from "node:sqlite";
import { readdirSync, readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const ROOT = join(here, "..", "..");
export const CONTRACT = JSON.parse(readFileSync(join(ROOT, "schemas", "live-contract.json"), "utf8"));
const FIX = join(ROOT, "tests", "fixtures", "live");
export const fixture = (rel) => JSON.parse(readFileSync(join(FIX, rel), "utf8"));

class Statement {
  constructor(db, sql, args = []) { this.db = db; this.sql = sql; this.args = args; }
  bind(...args) { return new Statement(this.db, this.sql, args); }
  async first() { return this.db.prepare(this.sql).get(...this.args) ?? null; }
  async all() { return { results: this.db.prepare(this.sql).all(...this.args), success: true }; }
  async run() { const r = this.db.prepare(this.sql).run(...this.args); return { success: true, meta: { changes: Number(r.changes) } }; }
}

export function localD1({ seed = true } = {}) {
  const db = new DatabaseSync(":memory:");
  for (const f of readdirSync(join(ROOT, "web", "migrations")).filter((n) => n.endsWith(".sql")).sort()) {
    db.exec(readFileSync(join(ROOT, "web", "migrations", f), "utf8"));
  }
  const d1 = {
    db,
    prepare: (sql) => new Statement(db, sql),
    async batch(stmts) {
      db.exec("begin");
      try { const out = []; for (const s of stmts) out.push(await s.run()); db.exec("commit"); return out; }
      catch (e) { db.exec("rollback"); throw e; }
    },
  };
  if (seed) for (const table of Object.keys(CONTRACT.tables)) seedTable(db, table, fixture(`tables/${table}.json`));
  return d1;
}

export function seedTable(db, table, rows) {
  for (const row of rows) {
    const cols = Object.keys(row);
    const vals = cols.map((c) => { const v = row[c]; return typeof v === "boolean" ? Number(v) : v !== null && typeof v === "object" ? JSON.stringify(v) : v; });
    db.prepare(`insert or replace into ${table} (${cols.join(",")}) values (${cols.map(() => "?").join(",")})`).run(...vals);
  }
}

// Check a value against the contract's shape language (schemas/live-contract.json, shape_language).
export function problems(value, shape, path = "$") {
  if (Array.isArray(shape)) {
    if (!Array.isArray(value)) return [`${path}: expected list`];
    return value.flatMap((v, i) => problems(v, shape[0], `${path}[${i}]`));
  }
  if (shape && typeof shape === "object") {
    if (!value || typeof value !== "object" || Array.isArray(value)) return [`${path}: expected object`];
    const known = new Set(Object.keys(shape).map((k) => k.replace(/\?$/, "")));
    const bad = Object.keys(value).filter((k) => !known.has(k)).map((k) => `${path}.${k}: not in contract`);
    for (const [k, s] of Object.entries(shape)) {
      const name = k.replace(/\?$/, "");
      if (!(name in value)) { if (!k.endsWith("?")) bad.push(`${path}.${name}: missing`); continue; }
      bad.push(...problems(value[name], s, `${path}.${name}`));
    }
    return bad;
  }
  const nullable = shape.endsWith("?"), base = nullable ? shape.slice(0, -1) : shape;
  if (value === null) return nullable ? [] : [`${path}: null`];
  const en = base.match(/^enum\((.*)\)$/);
  const ok = en ? en[1].split("|").includes(value)
    : base === "str" || base === "time" || base === "date" ? typeof value === "string"
    : base === "int" ? Number.isInteger(value)
    : base === "num" ? typeof value === "number"
    : base === "bool" ? typeof value === "boolean"
    : base === "json" ? true : false;
  return ok ? [] : [`${path}: ${JSON.stringify(value)} is not ${base}`];
}
export const route = (id) => CONTRACT.routes.find((r) => r.id === id);
