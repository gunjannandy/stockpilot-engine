// Migration runner: timestamp-named SQL, expand-then-contract (decisions §2, story 138).
// Expand steps only add; the Worker applies them before its first request. Contract steps
// (`*.contract.sql`) may drop, run only when asked, and only after a backup is recorded.
// The bookkeeping table is wrangler's own, so `wrangler d1 migrations apply` (previews) and this
// runner (production, Node) agree on what has run.

export type Migration = { name: string; sql: string };
type Db = {
  prepare(sql: string): { bind(...v: unknown[]): unknown; all(): Promise<{ results: unknown[] }> };
  exec(sql: string): Promise<unknown>;
  batch(statements: never[]): Promise<unknown>;
};

const BACKUP_MAX_AGE_MS = 6 * 3600 * 1000;

/** SQL with comments and string literals blanked, so a word in either never trips the check. */
function bare(sql: string): string {
  return sql
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .replace(/--[^\n]*/g, " ")
    .replace(/'(?:[^']|'')*'/g, "''")
    .toLowerCase();
}

export function isExpandOnly(sql: string): boolean {
  const s = bare(sql);
  return !/\b(drop\s+(table|index|view|trigger|column)|rename\s+(to|column)|delete\s+from|truncate)\b/.test(
    s,
  );
}

export const isContractStep = (name: string) => name.endsWith(".contract.sql");

export async function appliedNames(db: Db): Promise<Set<string>> {
  await db.exec(
    "create table if not exists d1_migrations (id integer primary key autoincrement, name text unique, applied_at timestamp not null default current_timestamp)",
  );
  const rows = (await db.prepare("select name from d1_migrations").all()).results as {
    name: string;
  }[];
  return new Set(rows.map((r) => r.name));
}

/** Pending steps in name order. `contract: true` runs contract steps too (and needs `backupAt`). */
export async function applyPending(
  db: Db,
  migrations: Migration[],
  opts: { contract?: boolean; backupAt?: Date; now?: Date } = {},
): Promise<string[]> {
  const done = await appliedNames(db);
  const pending = [...migrations]
    .sort((a, b) => a.name.localeCompare(b.name))
    .filter((m) => !done.has(m.name))
    .filter((m) => opts.contract || !isContractStep(m.name));
  // Check everything before running anything: a refused step leaves the database as it was.
  for (const m of pending) {
    if (isContractStep(m.name)) {
      const age =
        (opts.now ?? new Date()).getTime() - (opts.backupAt?.getTime() ?? Number.NEGATIVE_INFINITY);
      if (!(age >= 0 && age <= BACKUP_MAX_AGE_MS))
        throw new Error(`contract step ${m.name} needs a backup taken in the last 6 hours`);
    } else if (!isExpandOnly(m.sql)) {
      throw new Error(
        `${m.name} is an expand step and may not drop, rename or delete; use a .contract.sql step`,
      );
    }
  }
  const ran: string[] = [];
  for (const m of pending) {
    // D1 refuses BEGIN/COMMIT; a batch is its atomic unit. The bookkeeping row rides in the same batch.
    const statements = splitStatements(m.sql).map((q) => db.prepare(q));
    statements.push(
      db.prepare("insert into d1_migrations (name) values (?)").bind(m.name) as never,
    );
    await db.batch(statements as never[]);
    ran.push(m.name);
  }
  return ran;
}

/** One statement per entry. Migrations here are plain DDL, so a semicolon always ends a statement. */
export function splitStatements(sql: string): string[] {
  return sql
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .replace(/--[^\n]*/g, " ")
    .split(";")
    .map((q) => q.trim())
    .filter(Boolean);
}
