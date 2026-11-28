// Feedback asks (FEEDBACK area). Private: previews hold made-up rows only.
import { integer, sqliteTable, text } from "drizzle-orm/sqlite-core";

export const feedback = sqliteTable("feedback", {
  id: text("id").primaryKey(),
  text: text("text").notNull(),
  understanding: text("understanding"),
  status: text("status").notNull().default("received"),
  ticket: integer("ticket"),
  staleTicket: integer("stale_ticket"),
  createdAt: text("created_at").notNull(),
  reviewedAt: text("reviewed_at"),
  updatedAt: text("updated_at").notNull(),
});
