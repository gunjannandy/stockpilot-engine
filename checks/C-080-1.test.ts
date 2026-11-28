// C-080-1: a consumer reading the raw sector tag fails the contract test.
import { expect, it } from "vitest";
import { rawTagReads } from "../api/src/news/contract";

it("C-080-1 raw tag reads are caught", () => {
  expect(rawTagReads("select * from news_tags where symbol = ?")).not.toEqual([]);
  expect(rawTagReads("const s = item.sector;")).not.toEqual([]);
  expect(rawTagReads("select * from news_items where sector = 'Banks'")).not.toEqual([]);
  expect(rawTagReads("const rows = await readImpact(d1, { symbols });")).toEqual([]);
});
