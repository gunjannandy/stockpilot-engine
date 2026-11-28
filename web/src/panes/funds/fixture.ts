// Made-up funds for the prototype and its tests: nothing here is real market data or real holdings.
import type { Lot, Series } from "./funds-core";

export type Fund = {
  id: string;
  name: string;
  amc: string;
  category: string;
  /** Yearly cost, percent of the money in the fund. */
  cost: number;
  /** Fund size in crore rupees; null when no source gives it. */
  size: number | null;
  series: Series;
  /** The middle fund of its kind, same dates. */
  kind: Series;
  lots: Lot[];
};

const END = Date.parse("2026-11-26");
const WEEKS = 560;
function dates(): string[] {
  const out: string[] = [];
  for (let i = WEEKS; i >= 0; i--)
    out.push(new Date(END - i * 7 * 86_400_000).toISOString().slice(0, 10));
  return out;
}
const D = dates();

/** Deterministic wobbly growth: yearly drift plus waves, with the three bad markets pressed in. */
function make(seed: number, drift: number, wave: number, start = 0): Series {
  const nav: number[] = [];
  let v = 100;
  for (let i = start; i < D.length; i++) {
    const when = Date.parse(D[i] as string);
    let shock = 0;
    if (when > Date.parse("2008-01-08") && when < Date.parse("2009-03-09")) shock = -0.012;
    if (when > Date.parse("2020-01-20") && when < Date.parse("2020-03-23")) shock = -0.028;
    if (when > Date.parse("2021-10-19") && when < Date.parse("2022-06-17")) shock = -0.004;
    if (when > Date.parse("2009-03-09") && when < Date.parse("2010-03-01")) shock = 0.011;
    v *=
      1 +
      drift / 52 +
      shock * (0.6 + wave) +
      Math.sin(i * 0.37 + seed) * 0.006 * wave +
      Math.cos(i * 0.11 + seed * 2) * 0.004 * wave;
    nav.push(Math.round(v * 100) / 100);
  }
  return { dates: D.slice(start), nav };
}

export const NIFTY: Series = make(1, 0.115, 0.9);

const mk = (
  id: string,
  name: string,
  amc: string,
  category: string,
  cost: number,
  size: number | null,
  seed: number,
  drift: number,
  wave: number,
  kindDrift: number,
  start: number,
  lots: Lot[],
): Fund => ({
  id,
  name,
  amc,
  category,
  cost,
  size,
  series: make(seed, drift, wave, start),
  kind: make(seed + 40, kindDrift, 0.85, start),
  lots,
});

export const FUNDS: Fund[] = [
  mk(
    "kestrel-flexi",
    "Kestrel Flexi Cap Fund",
    "Kestrel",
    "Flexi cap",
    0.62,
    14800,
    2,
    0.14,
    0.85,
    0.118,
    0,
    [
      { acquired_on: "2021-03-12", quantity: 120.5, cost: 24000 },
      { acquired_on: "2023-01-20", quantity: 80.2, cost: 20000 },
      { acquired_on: "2025-06-06", quantity: 60.1, cost: 18000 },
    ],
  ),
  mk(
    "maple-index",
    "Maple Nifty 50 Index Fund",
    "Maple",
    "Index",
    0.18,
    22100,
    3,
    0.115,
    0.9,
    0.115,
    120,
    [
      { acquired_on: "2022-08-05", quantity: 300.4, cost: 40000 },
      { acquired_on: "2024-04-12", quantity: 150, cost: 25000 },
    ],
  ),
  mk(
    "harbor-small",
    "Harbor Small Cap Fund",
    "Harbor",
    "Small cap",
    0.71,
    9100,
    4,
    0.19,
    1.1,
    0.16,
    0,
    [{ acquired_on: "2020-09-18", quantity: 90, cost: 10000 }],
  ),
  mk(
    "delta-bluechip",
    "Delta Large Cap Fund",
    "Delta",
    "Large cap",
    0.85,
    31200,
    5,
    0.098,
    0.8,
    0.108,
    0,
    [],
  ),
  mk(
    "orbit-midcap",
    "Orbit Mid Cap Fund",
    "Orbit",
    "Mid cap",
    0.74,
    19800,
    6,
    0.17,
    1.0,
    0.15,
    60,
    [{ acquired_on: "2023-07-14", quantity: 70.3, cost: 15000 }],
  ),
  mk(
    "pine-debt",
    "Pine Short Duration Fund",
    "Pine",
    "Short debt",
    0.34,
    11700,
    7,
    0.068,
    0.08,
    0.066,
    0,
    [],
  ),
  mk(
    "quartz-elss",
    "Quartz Tax Saver Fund",
    "Quartz",
    "Tax saver (ELSS)",
    0.9,
    6400,
    8,
    0.135,
    0.9,
    0.125,
    0,
    [{ acquired_on: "2024-03-22", quantity: 55, cost: 12000 }],
  ),
  mk(
    "sable-new",
    "Sable Focused Fund",
    "Sable",
    "Focused",
    0.88,
    null,
    9,
    0.12,
    0.9,
    0.118,
    420,
    [],
  ),
];
