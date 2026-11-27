import { expect, it } from "vitest";
import { d1Bytes } from "./routes";

const ctxWith = (prepare: (sql: string) => unknown) => ({ d1: { prepare } }) as never;

it("D1 size falls back to the size D1 reports when it refuses the pragma", async () => {
  const bytes = await d1Bytes(
    ctxWith((sql) => {
      if (sql.includes("pragma")) throw new Error("SQLITE_AUTH");
      return { all: async () => ({ meta: { size_after: 4096 } }) };
    }),
  );
  expect(bytes).toBe(4096);
});

it("D1 size is 0, not an error, when no size is available", async () => {
  expect(
    await d1Bytes(
      ctxWith(() => {
        throw new Error("no");
      }),
    ),
  ).toBe(0);
});
