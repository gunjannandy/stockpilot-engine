// The word-table rules, pure so a unit test and the build guard share them.
// Every fixed word (a key in an area's English file) must exist in Bengali, and nothing extra may sit in Bengali.
export type WordFiles = Record<string, Record<string, string>>; // "<area>.<lang>" -> key -> text

export function missingBengali(en: Record<string, string>, bn: Record<string, string>): string[] {
  return Object.keys(en).filter((k) => !(bn[k] ?? "").trim());
}

/** Problems across all words files, e.g. `shell.search: no Bengali`. Empty means complete. */
export function wordProblems(files: WordFiles): string[] {
  const out: string[] = [];
  const areas = new Set(Object.keys(files).map((f) => f.replace(/\.(en|bn)$/, "")));
  for (const a of [...areas].sort()) {
    const en = files[`${a}.en`] ?? {};
    const bn = files[`${a}.bn`] ?? {};
    for (const k of missingBengali(en, bn)) out.push(`${a}.${k}: no Bengali`);
    for (const k of Object.keys(bn)) if (!(k in en)) out.push(`${a}.${k}: Bengali without English`);
  }
  return out;
}

/** Throws when any fixed word lacks Bengali. */
export function assertWordsComplete(files: WordFiles): void {
  const p = wordProblems(files);
  if (p.length) throw new Error(`words incomplete:\n${p.join("\n")}`);
}
