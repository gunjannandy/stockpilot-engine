// C-023-3: a changed verdict or chance marks the stock; news without a change shows the newspaper icon, not a mark.
import { diffRows, hasNews } from "../contract/src/marks/marks";
import { expect, it } from "vitest";

const row = (o: object) => ({
  symbol: "AAA",
  call: "keep",
  chance_3m: 60,
  news: 0,
  as_of: "d1",
  ...o,
});

it("C-023-3 a changed call or chance marks the stock", () => {
  expect(diffRows([row({})], [row({ call: "sell", as_of: "d2" })])).toEqual([
    { key: "AAA", fields: ["call"], isNew: false },
  ]);
  expect(diffRows([row({})], [row({ chance_3m: 45 })])[0]?.fields).toEqual(["chance_3m"]);
});

it("C-023-3 news without a change is a newspaper icon, never a mark", () => {
  const before = [row({})];
  const after = [row({ news: 2, as_of: "d2" })];
  expect(diffRows(before, after)).toEqual([]);
  expect(hasNews(after[0] as never)).toBe(true);
});
