// Small readers shared by the maps. v2 stored naive timestamps; they are IST.
export const IST_ZERO = "1970-01-01T05:30:00+05:30";
export const ist = (v: unknown): string => {
  if (v === null || v === undefined || v === "") return IST_ZERO;
  const s = v instanceof Date ? v.toISOString() : String(v);
  if (/[zZ]|[+-]\d\d:\d\d$/.test(s)) return s;
  return `${s.replace(" ", "T").replace(/\.\d+$/, "")}+05:30`;
};
export const dayOf = (v: unknown): string =>
  String(v instanceof Date ? v.toISOString() : v).slice(0, 10);
/** A JSON column may arrive as text or already parsed. */
export const parse = (v: unknown): unknown => {
  if (typeof v !== "string") return v;
  try {
    return JSON.parse(v);
  } catch {
    return null;
  }
};
export const num = (v: unknown): number | null =>
  v === null || v === undefined || v === "" || !Number.isFinite(Number(v)) ? null : Number(v);
export const exchange = (v: unknown): "NSE" | "BSE" => (v === "BSE" ? "BSE" : "NSE");
