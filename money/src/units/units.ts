// The nightly unit check. Kite says how many units are owned; the lots (built from the owners'
// documents) must explain every one of them. A difference is a bug in what we read, never a normal
// state: each one is named in plain words. US shares are not Kite's, so they are not checked here.
// A port of Python `book/units.py`.
import { canon, isForeign } from "../core/kinds";
import { kiteHoldings } from "../lots/rebuild";
import type { KiteSnapshot } from "../lots/types";
import { unitText as u } from "./positions";

export const TOLERANCE = 0.0005; // a fund unit has three decimals

export type Gap = { isin: string; symbol: string; kite: number; lots: number; message: string };
export type UnitLot = {
  kind: string;
  symbol: string;
  isin: string | null;
  quantity: number;
  closedQuantity: number;
  currency: string | null;
};

const SEP = "\u0000";

function message(symbol: string, kite: number, lots: number): string {
  if (!lots)
    return `${symbol}: Kite shows ${u(kite)} units, no document explains any (${u(kite)} unexplained).`;
  if (!kite)
    return `${symbol}: the documents show ${u(lots)} units, Kite shows none (${u(lots)} unexplained).`;
  if (kite > lots) {
    return `${symbol}: Kite shows ${u(kite)} units, the documents explain ${u(lots)} (${u(kite - lots)} unexplained).`;
  }
  return `${symbol}: the documents show ${u(lots)} units, Kite shows ${u(kite)} (${u(lots - kite)} unexplained).`;
}

/** Every holding whose units in the lots differ from Kite's latest snapshot. No snapshot, nothing to check. */
export function gaps(input: {
  lots: readonly UnitLot[];
  kite: KiteSnapshot | null;
  stocks: readonly { symbol: string; isin: string | null }[];
}): Gap[] {
  const kite = input.kite ? kiteHoldings(input.kite.rows) : new Map();
  if (kite.size === 0) return [];
  const mine = new Map<string, { symbol: string; qty: number }>();
  for (const l of input.lots) {
    const qty = l.quantity - l.closedQuantity;
    if (!(qty > 1e-9)) continue;
    if (isForeign({ kind: l.kind, currency: l.currency || "INR" })) continue;
    const key = `${canon(l.kind)}${SEP}${l.isin || l.symbol}`;
    const old = mine.get(key) ?? { symbol: l.symbol, qty: 0.0 };
    mine.set(key, { symbol: old.symbol, qty: old.qty + qty });
  }
  const names = new Map<string, string>();
  for (const s of input.stocks) if (s.isin) names.set(s.isin, s.symbol);
  const keys = [...new Set([...kite.keys(), ...mine.keys()])].sort((a, b) => {
    const [x, y] = [tupleStr(a), tupleStr(b)];
    return x < y ? -1 : x > y ? 1 : 0;
  });
  const out: Gap[] = [];
  for (const key of keys) {
    const k = kite.get(key);
    const m = mine.get(key);
    const kQty = k?.qty ?? 0.0;
    const lQty = m?.qty ?? 0.0;
    if (Math.abs(kQty - lQty) <= TOLERANCE) continue;
    const isin = key.split(SEP)[1] as string;
    const symbol = names.get(isin) || m?.symbol || (k?.symbol as string);
    out.push({ isin, symbol, kite: kQty, lots: lQty, message: message(symbol, kQty, lQty) });
  }
  return out;
}

const tupleStr = (key: string): string => {
  const [a, b] = key.split(SEP);
  return `('${a}', '${b}')`;
};

/** The doctor's shape: ONE fault for all gaps, so a first night with many does not file a pile of issues. */
export function findings(
  found: readonly Gap[],
): { key: string; summary: string; detail: string }[] {
  if (found.length === 0) return [];
  const lines = found.map((g) => `- ${g.message}`).join("\n");
  return [
    {
      key: "units-mismatch",
      summary: `${found.length} holding${found.length !== 1 ? "s" : ""}: units in the documents differ from Kite`,
      detail: `Kite decides what is owned; the lots built from the documents must explain every unit. Find which document is missing or misread.\n${lines}`,
    },
  ];
}
