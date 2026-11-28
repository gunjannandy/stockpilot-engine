// Fuzzy stock search over the search index file. Fuse runs over the small list of distinct words
// (symbols and name words), each typed word is matched alone and a stock must match every word.
import Fuse from "fuse.js";

export type Entry = { symbol: string; name: string; exchange?: string };

const norm = (s: string) =>
  String(s ?? "")
    .toLowerCase()
    .replace(/[^a-z0-9 ]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
const SKIP = new Set(["limited", "ltd", "the", "of", "and"]);

export function createSearch(entries: Entry[], limit = 8) {
  const vocab = new Map<string, number[]>();
  const put = (w: string, i: number) => {
    const a = vocab.get(w) ?? [];
    if (a[a.length - 1] !== i) a.push(i);
    vocab.set(w, a);
  };
  entries.forEach((e, i) => {
    put(e.symbol.toLowerCase(), i);
    for (const w of norm(e.name).split(" ")) if (w && !SKIP.has(w)) put(w, i);
  });
  const words = [...vocab.keys()];
  const fuse = new Fuse(
    words.map((t) => ({ t })),
    {
      keys: ["t"],
      includeScore: true,
      threshold: 0.4,
      ignoreLocation: true,
      minMatchCharLength: 2,
    },
  );
  const symIdx = new Map(entries.map((e, i) => [e.symbol.toLowerCase(), i]));

  function perWord(q: string): Map<number, number> {
    const out = new Map<number, number>();
    const add = (w: string, s: number) => {
      for (const i of vocab.get(w) ?? []) if (!((out.get(i) ?? Infinity) <= s)) out.set(i, s);
    };
    for (const w of words) if (w.startsWith(q)) add(w, 0.02 + 0.2 * (1 - q.length / w.length));
    if (q.length >= 2)
      for (const h of fuse.search(q, { limit: 80 }))
        add(words[h.refIndex] as string, (h.score ?? 0) + 0.1);
    return out;
  }
  return {
    find(query: string): Entry[] {
      const qs = norm(query).split(" ").filter(Boolean);
      if (!qs.length) return [];
      let acc: Map<number, number> | null = null;
      for (const q of qs) {
        const m = perWord(q);
        if (!acc) acc = m;
        else {
          const next = new Map<number, number>();
          for (const [i, s] of acc) if (m.has(i)) next.set(i, s + (m.get(i) as number));
          acc = next;
        }
        if (!acc.size) return [];
      }
      const exact = symIdx.get(qs.join(""));
      const ranked = [...(acc as Map<number, number>)].sort((a, b) => a[1] - b[1]).map((r) => r[0]);
      const idx = (exact === undefined ? [] : [exact]).concat(ranked.filter((i) => i !== exact));
      return idx.slice(0, limit).map((i) => entries[i] as Entry);
    },
  };
}
