// The ITR pack: same contents as py/stockpilot/analysis/tax.py `build_pack`, built in memory so the browser can
// download it (one zip, or the five files). Nothing here touches a disk or the network.
import type { Day } from "../core/dates";
import { isForeign } from "../core/kinds";
import {
  type Carried,
  type FaRow,
  fyLabel,
  GRANDFATHER_DATE,
  incomeTax,
  inputs,
  LONG_POOLS,
  type Net,
  netGains,
  type RateOn,
  type Row,
  realise,
  rulesFor,
  SHORT_POOLS,
  scheduleFa,
  type TaxLot,
  type TaxSale,
} from "../tax/tax";

const README = `Tax pack for FY {label}. Made by stockpilot; give it to whoever files the return.

Files
- summary.json      the year's gains after set-off, and the tax estimate
- schedule_112a.csv long-term equity and equity-fund sales, one line per ISIN and lot (the 112A / s.198 schedule)
- gains_detail.csv  every sale matched to its lot, oldest first
- schedule_fa.csv   foreign shares for calendar year {fy} (Schedule FA)

Form: {form}. ITR-3 instead if any F&O or intraday trading is treated as business income.

Read before relying on it
{warnings}
Gains use the oldest lot first, per ISIN. Compare the totals with Console's tax P&L before filing.
`;

function cell(v: unknown): string {
  const s =
    v === null || v === undefined ? "" : v === true ? "True" : v === false ? "False" : String(v);
  return /[",\r\n]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s;
}

/** CSV the way Python's csv module writes it: header first, `\r\n` line ends, quotes only where needed. */
export function csv(rows: Record<string, unknown>[], fields: string[]): string {
  return [fields.map(cell).join(","), ...rows.map((r) => fields.map((f) => cell(r[f])).join(","))]
    .map((l) => `${l}\r\n`)
    .join("");
}

export type PackInput = {
  lots: TaxLot[];
  sales: TaxSale[];
  fy: number;
  rateOn: RateOn;
  closes: Record<string, Record<Day, number>>;
  fmv2018?: Record<string, number>;
  carried?: Partial<Carried>[] | null;
  slabIncome?: number;
  fxRule?: string;
  fxNote?: string;
};

export type Pack = {
  itr_form: "ITR-2";
  summary: Record<string, unknown>;
  rows: Row[];
  net: Net;
  schedule_fa: FaRow[];
  files: Record<string, string>;
};

export function buildPack(p: PackInput): Pack {
  const { fy } = p;
  const rules = rulesFor(fy);
  const start = `${fy}-04-01`;
  const end = `${fy + 1}-03-31`;
  const rows = realise(
    p.lots,
    p.sales,
    p.fmv2018 ?? {},
    p.rateOn,
    p.fxRule ?? "prior_month_end",
  ).filter((r) => r.sold_on >= start && r.sold_on <= end);
  const net = netGains(rows, rules, fy, p.carried ?? null);
  const estimate = incomeTax(inputs(net, p.slabIncome ?? 0), rules);
  const warnings = [...estimate.warnings];
  for (const r of rows) {
    if (r.bucket === "equity" && r.acquired_on < GRANDFATHER_DATE && !r.grandfathered) {
      warnings.push(
        `${r.symbol}: bought before 1 Feb 2018 and no 31 Jan 2018 price on file, so actual cost was used. This can overstate the gain.`,
      );
    }
  }
  warnings.push(
    "Rules for FY 2026-27 are partly unconfirmed (Finance Act 2026 text, FX-date rule, ITR layouts): see docs/research/tax-rules.md section 11.",
  );
  if (p.fxNote) {
    warnings.push(
      `USD/INR rates: ${p.fxNote}. Schedule FA wants the SBI TT buying rate; check the figures against it.`,
    );
  }
  const fa = p.lots.some((l) => isForeign(l))
    ? scheduleFa(p.lots, p.sales, fy, p.closes, p.rateOn)
    : [];
  const summary = {
    fy: fyLabel(fy),
    form: "ITR-2",
    ...Object.fromEntries([...SHORT_POOLS, ...LONG_POOLS].map((k) => [k, net[k]])),
    carry_forward: net.carry_forward,
    expired_losses: net.expired,
    tax: estimate,
    sales_counted: rows.length,
    warnings,
  };
  const files: Record<string, string> = {
    "gains_detail.csv": csv(rows, [
      "symbol",
      "isin",
      "bucket",
      "term",
      "acquired_on",
      "sold_on",
      "quantity",
      "cost",
      "proceeds",
      "expenses",
      "gain",
      "grandfathered",
    ]),
    "schedule_112a.csv": csv(
      rows.filter((r) => r.bucket === "equity" && r.term === "long"),
      [
        "isin",
        "symbol",
        "acquired_on",
        "sold_on",
        "quantity",
        "proceeds",
        "cost",
        "expenses",
        "gain",
        "grandfathered",
      ],
    ),
    "schedule_fa.csv": csv(fa, [
      "symbol",
      "isin",
      "units_at_close",
      "initial_value",
      "peak_value",
      "closing_value",
      "gross_proceeds",
      "note",
    ]),
    "summary.json": JSON.stringify(summary, null, 2),
    "README.txt": README.replace("{label}", fyLabel(fy))
      .replace("{fy}", String(fy))
      .replace("{form}", "ITR-2")
      .replace("{warnings}", () => warnings.map((w) => `- ${w}`).join("\n")),
  };
  return { itr_form: "ITR-2", summary, rows, net, schedule_fa: fa, files };
}

// --- one-file download: a store-only zip ------------------------------------------------------

const CRC = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();

function crc32(b: Uint8Array): number {
  let c = 0xffffffff;
  for (const x of b) c = (CRC[(c ^ x) & 0xff] as number) ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

/** The pack as one zip file's bytes (no compression: the files are small text). */
export function packZip(files: Record<string, string>): Uint8Array {
  const enc = new TextEncoder();
  const chunks: Uint8Array[] = [];
  const central: Uint8Array[] = [];
  let offset = 0;
  const u16 = (n: number) => [n & 0xff, (n >>> 8) & 0xff];
  const u32 = (n: number) => [n & 0xff, (n >>> 8) & 0xff, (n >>> 16) & 0xff, (n >>> 24) & 0xff];
  for (const [name, text] of Object.entries(files)) {
    const nameB = enc.encode(name);
    const data = enc.encode(text);
    const crc = crc32(data);
    const common = [
      ...u16(20),
      ...u16(0x0800),
      ...u16(0),
      ...u16(0),
      ...u16(0x21),
      ...u32(crc),
      ...u32(data.length),
      ...u32(data.length),
      ...u16(nameB.length),
      ...u16(0),
    ];
    const local = new Uint8Array([0x50, 0x4b, 3, 4, ...common, ...nameB]);
    chunks.push(local, data);
    central.push(
      new Uint8Array([
        0x50,
        0x4b,
        1,
        2,
        ...u16(20),
        ...common,
        ...u16(0),
        ...u16(0),
        ...u16(0),
        ...u32(0),
        ...u32(offset),
        ...nameB,
      ]),
    );
    offset += local.length + data.length;
  }
  const cd = central.reduce((n, c) => n + c.length, 0);
  const end = new Uint8Array([
    0x50,
    0x4b,
    5,
    6,
    ...u16(0),
    ...u16(0),
    ...u16(central.length),
    ...u16(central.length),
    ...u32(cd),
    ...u32(offset),
    ...u16(0),
  ]);
  const all = [...chunks, ...central, end];
  const out = new Uint8Array(all.reduce((n, c) => n + c.length, 0));
  let at = 0;
  for (const c of all) {
    out.set(c, at);
    at += c.length;
  }
  return out;
}
