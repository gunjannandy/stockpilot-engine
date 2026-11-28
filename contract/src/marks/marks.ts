import { z } from "zod";

/** Fields that move on every run and so never count as a change. */
const NOISE = /(^|_)(at|as_of|run_id|seq)$/;

export const MarkItem = z.object({
  dataset: z.string().min(1),
  key: z.string().min(1),
  /** The run that made this change; a later change to the same row is a new mark. */
  runId: z.string().min(1),
  /** Which fields differ from the previous run (empty for a row that is new). */
  fields: z.array(z.string()),
  isNew: z.boolean(),
  seen: z.boolean(),
});
export type MarkItem = z.infer<typeof MarkItem>;

export const MarksAnswer = z.object({
  items: z.array(MarkItem),
  unseen: z.number().int(),
  /** Rows with news but no change: they get the newspaper icon, never a mark. */
  news: z.array(z.object({ dataset: z.string(), key: z.string() })),
});
export type MarksAnswer = z.infer<typeof MarksAnswer>;

export const SeenBody = z.union([
  z.object({ all: z.literal(true) }),
  z.object({ dataset: z.string().min(1), key: z.string().min(1) }),
]);
export type SeenBody = z.infer<typeof SeenBody>;

type Row = Record<string, unknown>;
export const rowKey = (r: Row): string | null => {
  const k = r.symbol ?? r.id;
  return typeof k === "string" && k ? k : null;
};

/** Rows of `current` that differ from the same key in `previous`, or are new. With no previous run
 * there is nothing to compare, so nothing is marked. */
export function diffRows(
  previous: Row[] | null,
  current: Row[],
): { key: string; fields: string[]; isNew: boolean }[] {
  if (!previous) return [];
  const before = new Map<string, Row>();
  for (const r of previous) {
    const k = rowKey(r);
    if (k) before.set(k, r);
  }
  const out: { key: string; fields: string[]; isNew: boolean }[] = [];
  for (const r of current) {
    const key = rowKey(r);
    if (!key) continue;
    const old = before.get(key);
    if (!old) {
      out.push({ key, fields: [], isNew: true });
      continue;
    }
    const fields = [...new Set([...Object.keys(r), ...Object.keys(old)])]
      .filter(
        (f) => !NOISE.test(f) && f !== "news" && JSON.stringify(r[f]) !== JSON.stringify(old[f]),
      )
      .sort();
    if (fields.length) out.push({ key, fields, isNew: false });
  }
  return out;
}

/** A row is in the news when its `news` field is set (true, a count, or a non-empty list). */
export const hasNews = (r: Row): boolean =>
  Array.isArray(r.news) ? r.news.length > 0 : Boolean(r.news);
