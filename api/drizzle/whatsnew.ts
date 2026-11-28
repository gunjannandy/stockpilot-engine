// What's new (WORDS area): the notes promote.yml posts, and who has seen which.
import { integer, primaryKey, sqliteTable, text } from "drizzle-orm/sqlite-core";

export const whatsnew = sqliteTable("whatsnew", {
  pr: integer("pr").primaryKey(),
  en: text("en").notNull(),
  bn: text("bn").notNull(),
  at: text("at").notNull(),
});

export const whatsnewSeen = sqliteTable(
  "whatsnew_seen",
  {
    person: text("person").notNull(),
    pr: integer("pr").notNull(),
    at: text("at").notNull(),
  },
  (t) => [primaryKey({ columns: [t.person, t.pr] })],
);
