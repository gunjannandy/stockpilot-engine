// `pnpm new-area <name>`: every area starts from the same shape and touches no file outside its own
// folders and contract/ (story 149). `--registry` adds the dataset's line to the shared registry.
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

const NAME = /^[a-z][a-z0-9]{1,23}$/;
const stamp = (d: Date) => d.toISOString().replace(/[-:T]/g, "").slice(0, 14);
const Pascal = (s: string) => s[0]?.toUpperCase() + s.slice(1);

export function scaffold(
  root: string,
  name: string,
  opts: { registry?: boolean; now?: Date } = {},
): string[] {
  if (!NAME.test(name)) throw new Error(`area name "${name}" must be lowercase letters and digits`);
  const P = Pascal(name);
  const ts = stamp(opts.now ?? new Date());
  const files: Record<string, string> = {
    [`contract/src/${name}/${name}.ts`]: `import { z } from "zod";
import { IstTime } from "../core/time";

/** One ${name} row. Add fields only; the contract is additive (story 139). */
export const ${P}Row = z.object({
  id: z.string().min(1),
  at: IstTime,
});
export type ${P}Row = z.infer<typeof ${P}Row>;
`,
    [`api/src/${name}/schema.ts`]: `import { sqliteTable, text } from "drizzle-orm/sqlite-core";

export const ${name} = sqliteTable("${name}", {
  id: text("id").primaryKey(),
  at: text("at").notNull(),
});
`,
    [`api/src/${name}/migrations/${ts}_${name}.sql`]: `create table if not exists ${name} (id text primary key, at text not null);\n`,
    [`api/src/${name}/migration-map.json`]: `${JSON.stringify(
      { area: name, from_v2: [], note: "Per v2 table: copy, rebuild or drop, with the reason." },
      null,
      2,
    )}\n`,
    [`api/src/${name}/routes.ts`]: `import { Hono } from "hono";
import { ${name} } from "./schema";
import type { Ctx } from "../app";

export default function routes(ctx: Ctx) {
  const app = new Hono();
  app.get("/api/${name}", ctx.guard.person, async (c) => {
    return c.json({ rows: await ctx.db.select().from(${name}).limit(100) });
  });
  return app;
}
`,
    [`api/src/${name}/${name}.test.ts`]: `import { expect, it } from "vitest";
import { makeApp } from "../testkit";

it("${name} answers with no rows yet", async () => {
  const { app } = await makeApp();
  const res = await app.request("/api/${name}");
  expect(res.status).toBe(200);
  expect(await res.json()).toEqual({ rows: [] });
});
`,
    [`web/src/panes/${name}/index.tsx`]: `import type { Pane } from "../../areas";
import { useWords } from "../../words";

export function ${P}Pane() {
  const t = useWords();
  return (
    <section>
      <h1>{t("${name}.title")}</h1>
    </section>
  );
}

const pane: Pane = { id: "${name}", path: "/${name}", titleKey: "${name}.title", Component: ${P}Pane };
export default pane;
`,
    [`web/src/words/${name}.en.json`]: `${JSON.stringify({ title: P }, null, 2)}\n`,
    [`web/src/words/${name}.bn.json`]: `${JSON.stringify({ title: P }, null, 2)}\n`,
  };
  for (const rel of Object.keys(files))
    if (existsSync(join(root, rel)))
      throw new Error(`${rel} already exists; area "${name}" is taken`);
  for (const [rel, text] of Object.entries(files)) {
    mkdirSync(dirname(join(root, rel)), { recursive: true });
    writeFileSync(join(root, rel), text);
  }
  const written = Object.keys(files);
  if (opts.registry) {
    const reg = join(root, "contract/src/datasets.ts");
    const text = readFileSync(reg, "utf8");
    const end = text.lastIndexOf("} as const satisfies");
    if (end < 0) throw new Error("contract/src/datasets.ts has no registry to add to");
    const line = `  ${name}: {
    name: "${name}",
    job: "nightly",
    table: "${name}",
    schedule: "set when the area's Job exists",
    freshnessHours: 48,
    checks: { row: ["id is not empty", "at is IST"], run: [] },
    recomputable: false,
    writeBudget: 100,
    row: ${P}Row,
  },
`;
    const withImport = `import { ${P}Row } from "./${name}/${name}";\n${text.slice(0, end)}${line}${text.slice(end)}`;
    writeFileSync(reg, withImport);
    written.push("contract/src/datasets.ts");
  }
  return written;
}
