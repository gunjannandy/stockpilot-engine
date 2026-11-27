// First in, first out: close `qty` units against open lots in the order given; returns what no lot could cover.
import type { Lot } from "./types";

export const EPS = 1e-9;

export function sell(open: Lot[], qty: number): number {
  let left = qty;
  for (const lot of open) {
    if (left <= EPS) break;
    const take = Math.min(left, lot.qty - lot.closed);
    if (take > 0) {
      lot.closed += take;
      left -= take;
    }
  }
  return left;
}
