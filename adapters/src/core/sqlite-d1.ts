// A D1-shaped database over node:sqlite, so the Worker's code runs unchanged on Node and in tests
// (docker compose, decisions §2: never locked to one host). Only what drizzle and our routes call.
import { DatabaseSync } from "node:sqlite";

type Param = string | number | bigint | null | Uint8Array;
const bindable = (v: unknown): Param =>
  v === undefined || v === null ? null : typeof v === "boolean" ? (v ? 1 : 0) : (v as Param);

export class SqliteStatement {
  constructor(
    private readonly db: DatabaseSync,
    readonly sql: string,
    private readonly params: Param[] = [],
  ) {}
  bind(...values: unknown[]) {
    return new SqliteStatement(this.db, this.sql, values.map(bindable));
  }
  private meta(changes = 0, lastRowId = 0) {
    return { changes, last_row_id: lastRowId, rows_written: changes, rows_read: 0, duration: 0 };
  }
  runSync() {
    const r = this.db.prepare(this.sql).run(...this.params);
    return {
      results: [],
      success: true as const,
      meta: this.meta(Number(r.changes), Number(r.lastInsertRowid)),
    };
  }
  async run() {
    return this.runSync();
  }
  async all<T = Record<string, unknown>>() {
    const results = this.db.prepare(this.sql).all(...this.params) as T[];
    return { results, success: true as const, meta: this.meta() };
  }
  async first<T = Record<string, unknown>>(column?: string): Promise<T | null> {
    const row = this.db.prepare(this.sql).get(...this.params) as
      | Record<string, unknown>
      | undefined;
    if (!row) return null;
    return (column ? row[column] : row) as T;
  }
  async raw<T = unknown[]>(): Promise<T[]> {
    const st = this.db.prepare(this.sql);
    st.setReturnArrays(true);
    return st.all(...this.params) as T[];
  }
}

export class SqliteD1 {
  readonly raw: DatabaseSync;
  constructor(path = ":memory:") {
    this.raw = new DatabaseSync(path);
    this.raw.exec("pragma journal_mode = wal; pragma foreign_keys = on;");
  }
  prepare(sql: string) {
    return new SqliteStatement(this.raw, sql);
  }
  async exec(sql: string) {
    this.raw.exec(sql);
    return { count: 1, duration: 0 };
  }
  /** All statements or none, as D1's batch. */
  async batch(statements: SqliteStatement[]) {
    this.raw.exec("begin");
    try {
      const out = statements.map((s) => s.runSync());
      this.raw.exec("commit");
      return out;
    } catch (err) {
      this.raw.exec("rollback");
      throw err;
    }
  }
  close() {
    this.raw.close();
  }
}
