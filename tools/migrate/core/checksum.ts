import { createHash } from "node:crypto";
import type { Row } from "./types";

const canon = (v: unknown): unknown =>
  Array.isArray(v)
    ? v.map(canon)
    : v && typeof v === "object"
      ? Object.fromEntries(
          Object.entries(v)
            .sort(([a], [b]) => (a < b ? -1 : 1))
            .map(([k, x]) => [k, canon(x)]),
        )
      : v === undefined
        ? null
        : v;

const MOD = 1n << 256n;

/** Order-free, streaming fingerprint of a set of rows: the count and the sum of each row's sha256. */
export class Fingerprint {
  count = 0;
  private sum = 0n;
  add(row: Row): void {
    const h = createHash("sha256")
      .update(JSON.stringify(canon(row)))
      .digest("hex");
    this.sum = (this.sum + BigInt(`0x${h}`)) % MOD;
    this.count++;
  }
  get sha(): string {
    return this.sum.toString(16).padStart(64, "0");
  }
}
