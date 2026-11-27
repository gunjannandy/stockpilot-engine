// Shared by the money checks: loads what tools/capture/capture.py saved from the Python.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

export function captured<T>(file: string): T[] {
  return JSON.parse(readFileSync(join(here, "../money/captured", file), "utf8")) as T[];
}

/** Order-free comparison key: the Python replays demerger children in set order, which is arbitrary. */
const sortKeys = (v: unknown): unknown =>
  Array.isArray(v)
    ? v.map(sortKeys)
    : v && typeof v === "object"
      ? Object.fromEntries(
          Object.entries(v as Record<string, unknown>)
            .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
            .map(([k, x]) => [k, sortKeys(x)]),
        )
      : v;
export const canonical = (rows: unknown[]): string[] =>
  rows.map((r) => JSON.stringify(sortKeys(r))).sort();
