// C-081-1: each named consumer reads the impact table, never the raw sector tag.
import { readFileSync } from "node:fs";
import { expect, it } from "vitest";
import { CONSUMER_FILES, rawTagReads, readsImpactTable } from "../api/src/news/contract";
import { NEWS_CONSUMERS } from "../contract/src/news/news";

it("C-081-1 every named consumer is registered, and each registered file reads impact only", () => {
  expect(Object.keys(CONSUMER_FILES).sort()).toEqual([...NEWS_CONSUMERS].sort());
  for (const [name, files] of Object.entries(CONSUMER_FILES))
    for (const f of files) {
      const src = readFileSync(new URL(`../${f}`, import.meta.url), "utf8");
      expect(rawTagReads(src), `${name}: ${f}`).toEqual([]);
      expect(readsImpactTable(src), `${name}: ${f}`).toBe(true);
    }
});
