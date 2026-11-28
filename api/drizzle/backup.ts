// Backup and drill reports (decisions §4 Backup): one row per run, written by the private workflows.
import { index, integer, sqliteTable, text } from "drizzle-orm/sqlite-core";

export const backupReports = sqliteTable(
  "backup_reports",
  {
    id: integer("id").primaryKey({ autoIncrement: true }),
    kind: text("kind").notNull(), // 'backup' | 'drill'
    at: text("at").notNull(),
    ok: integer("ok", { mode: "boolean" }).notNull(),
    tables: text("tables").notNull(), // JSON: table -> { rows, sha256 }
    detail: text("detail").notNull(),
  },
  (t) => [index("backup_reports_kind_at").on(t.kind, t.at)],
);
