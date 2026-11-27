// The fake-data generator (story 146): realistic made-up rows for any Zod row schema, the same for the
// same seed. Tests, the Docker SQLite and the previews all draw from it; nothing in it is real.
import type { z } from "zod";
import { COMPANIES, FUNDS, SYMBOLS } from "../../fixtures/names";

type Rng = () => number;
// biome-ignore lint/suspicious/noExplicitAny: Zod's internal def is read structurally
type Def = any;

export const ANCHOR_DAY = Date.UTC(2026, 10, 20); // 2026-11-20, so output never depends on today

/** mulberry32: small, fast and good enough for sample rows. */
export function rng(seed: number): Rng {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const pick = <T>(r: Rng, xs: readonly T[]): T => xs[Math.floor(r() * xs.length)] as T;
const pad = (n: number) => String(n).padStart(2, "0");
const dayText = (r: Rng) => {
  const d = new Date(ANCHOR_DAY + Math.floor(r() * 30) * 86400000);
  return d.toISOString().slice(0, 10);
};
const istText = (r: Rng) =>
  `${dayText(r)}T${pad(9 + Math.floor(r() * 7))}:${pad(Math.floor(r() * 60))}:00+05:30`;

/** Strings: the first candidate the schema accepts, so regexes and formats are met without parsing them. */
function fakeString(schema: z.ZodType, key: string, row: number, r: Rng, seed: number): string {
  const k = key.toLowerCase();
  const named = /fund/.test(k)
    ? pick(r, FUNDS)
    : /symbol|ticker/.test(k)
      ? pick(r, SYMBOLS)
      : pick(r, COMPANIES);
  const candidates = [
    `fake-${seed}-${row}-${key}`,
    `${named} ${row}`,
    istText(r),
    dayText(r),
    `fake${row}@example.invalid`,
    `https://example.invalid/${key}/${row}`,
    String(100000 + row),
  ];
  for (const c of candidates) if (schema.safeParse(c).success) return c;
  throw new Error(`fake: no made-up string passes the schema for "${key}"`);
}

function value(schema: z.ZodType, key: string, row: number, r: Rng, seed: number): unknown {
  const def: Def = (schema as Def)._zod.def;
  switch (def.type) {
    case "object":
      return Object.fromEntries(
        Object.entries(def.shape as Record<string, z.ZodType>).map(([k, s]) => [
          k,
          value(s, k, row, r, seed),
        ]),
      );
    case "string":
      return fakeString(schema, key, row, r, seed);
    case "number": {
      const s = schema as Def;
      const int = Boolean(s.isInt) || /int/.test(def.format ?? "");
      const lo = Number.isFinite(s.minValue) ? (s.minValue as number) : 0;
      const hi = Number.isFinite(s.maxValue) ? (s.maxValue as number) : lo + 1000;
      if (int) return Math.ceil(lo) + Math.floor(r() * (Math.floor(hi) - Math.ceil(lo) + 1));
      return Math.round((lo + r() * (hi - lo)) * 100) / 100;
    }
    case "boolean":
      return r() < 0.5;
    case "enum":
      return pick(r, Object.values(def.entries));
    case "literal":
      return def.values[0];
    case "nullable":
    case "optional":
    case "default":
    case "prefault":
    case "readonly":
      return value(def.innerType, key, row, r, seed);
    case "pipe":
      return value(def.in, key, row, r, seed);
    case "array":
      return Array.from({ length: 1 + Math.floor(r() * 3) }, () =>
        value(def.element, key, row, r, seed),
      );
    case "union":
      return value(def.options[0], key, row, r, seed);
    default:
      throw new Error(`fake: no generator for ${def.type} at "${key}"`);
  }
}

/** `count` made-up rows for a Zod object schema. Same seed, same rows. */
export function fakeRows(schema: z.ZodType, count: number, seed = 1): Record<string, unknown>[] {
  const r = rng(seed);
  const rows = Array.from(
    { length: count },
    (_, i) => value(schema, "row", i, r, seed) as Record<string, unknown>,
  );
  for (const row of rows) {
    const p = schema.safeParse(row);
    if (!p.success) throw new Error(`fake: a made-up row fails the schema: ${p.error.message}`);
  }
  return rows;
}
