// Sign-in tables (the SIGNIN area): single-use link tokens and rate-limit counters.
import { integer, sqliteTable, text } from "drizzle-orm/sqlite-core";

/** One row per emailed link. `hash` is the SHA-256 of the token; the token itself is never stored. */
export const authLinks = sqliteTable("auth_links", {
  hash: text("hash").primaryKey(),
  person: text("person").notNull(),
  next: text("next").notNull(),
  expiresAt: integer("expires_at").notNull(),
});

/** A counter that starts at its first hit and runs for its window (unix seconds). */
export const authLimits = sqliteTable("auth_limits", {
  key: text("key").primaryKey(),
  n: integer("n").notNull(),
  until: integer("until").notNull(),
});
