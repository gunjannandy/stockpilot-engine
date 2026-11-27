// What a holding is. Writers store stock | mf | rsu; readers use equity | mf | foreign.
const CANON: Record<string, string> = {
  stock: "equity",
  equity: "equity",
  share: "equity",
  mf: "mf",
  fund: "mf",
  rsu: "foreign",
  foreign: "foreign",
  us: "foreign",
};

export function canon(kind: string | null | undefined): string {
  const k = (kind ?? "").toLowerCase();
  return CANON[k] ?? k;
}

/** Foreign shares (the RSUs): taxed as foreign, priced in dollars. */
export function isForeign(item: { kind?: string | null; currency?: string | null }): boolean {
  return canon(item.kind) === "foreign" || (item.currency || "INR") !== "INR";
}
