// Who has seen which What's new note (WORDS area). The notes themselves are health's `whatsnew` table.
import { integer, primaryKey, sqliteTable, text } from "drizzle-orm/sqlite-core";

export const whatsnewSeen = sqliteTable(
  "whatsnew_seen",
  {
    person: text("person").notNull(),
    pr: integer("pr").notNull(),
    at: text("at").notNull(),
  },
  (t) => [primaryKey({ columns: [t.person, t.pr] })],
);
