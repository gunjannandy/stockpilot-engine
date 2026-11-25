/* Fuzzy stock search over the full index (search/index.json), built on Fuse.js.
   Fuse runs over the small list of distinct words (symbols and name words), not over 9,000 full names, so a
   search stays well under 100 ms; each typed word is matched on its own and a stock must match every word. */
(function (root, factory) { root.SPSearch = factory(); })(globalThis, function () {
  const norm = s => String(s || "").toLowerCase().replace(/[^a-z0-9 ]+/g, " ").replace(/\s+/g, " ").trim();
  const SKIP = new Set(["limited", "ltd", "the", "of", "and"]);
  function createSearch(Fuse, entries, opts) {
    opts = opts || {};
    const limit = opts.limit || 8, boost = opts.boost || (() => 0);
    const vocab = new Map();                       // word -> doc indexes
    const put = (w, i) => { let a = vocab.get(w); if (!a) vocab.set(w, a = []); if (a[a.length - 1] !== i) a.push(i); };
    entries.forEach((e, i) => { put(String(e.symbol).toLowerCase(), i); for (const w of norm(e.name).split(" ")) if (w && !SKIP.has(w)) put(w, i); });
    const words = [...vocab.keys()];
    const fuse = new Fuse(words.map(t => ({ t })), { keys: ["t"], includeScore: true, threshold: 0.4, ignoreLocation: true, minMatchCharLength: 2 });
    const symIdx = new Map(entries.map((e, i) => [String(e.symbol).toLowerCase(), i]));

    function perWord(q) {                          // doc index -> score (lower is better) for one typed word
      const out = new Map(), add = (w, s) => { for (const i of vocab.get(w)) if (!(out.get(i) <= s)) out.set(i, s); };
      for (const w of words) if (w.startsWith(q)) add(w, 0.02 + 0.2 * (1 - q.length / w.length));
      if (q.length >= 2) for (const h of fuse.search(q, { limit: 80 })) add(words[h.refIndex], h.score + 0.1);
      return out;
    }
    return {
      find(query) {
        const qs = norm(query).split(" ").filter(Boolean); if (!qs.length) return [];
        let acc = null;
        for (const q of qs) {
          const m = perWord(q);
          if (!acc) acc = m; else { const next = new Map(); for (const [i, s] of acc) if (m.has(i)) next.set(i, s + m.get(i)); acc = next; }
          if (!acc.size) return [];
        }
        const exact = symIdx.get(qs.join(""));
        const ranked = [...acc].map(([i, s]) => [i, s - (boost(entries[i].symbol) ? 0.04 : 0)]).sort((a, b) => a[1] - b[1]);
        const idx = (exact === undefined ? [] : [exact]).concat(ranked.map(r => r[0]).filter(i => i !== exact));
        return idx.slice(0, limit).map(i => entries[i]);
      },
    };
  }
  return { createSearch };
});
