// Portfolio map: v2's vault holdings, trades, trade tags, Kite syncs and the corporate-action rows
// become v3's holdings, trades, trade_tags, kite_syncs, corporate_actions and action_terms.
// v2 stored naive timestamps; they are IST. v2 had one account.
import type { AreaMap, Row } from "./core/types";

const ACCOUNT = "main";

const ist = (v: unknown): string => {
  if (v === null || v === undefined || v === "") return "1970-01-01T05:30:00+05:30";
  const s = v instanceof Date ? v.toISOString() : String(v);
  if (/[zZ]|[+-]\d\d:\d\d$/.test(s)) return s;
  return `${s.replace(" ", "T").replace(/\.\d+$/, "")}+05:30`;
};
const day = (v: unknown): string => String(v instanceof Date ? v.toISOString() : v).slice(0, 10);
const text = (v: unknown): string | null =>
  v === null || v === undefined ? null : typeof v === "string" ? v : JSON.stringify(v);
const nul = (v: unknown) => (v === undefined ? null : v);
const num = (v: unknown) => (v === null || v === undefined ? null : Number(v));
const one = (dataset: string, row: Row) => ({ dataset, row });

const map: AreaMap = {
  area: "portfolio",
  tables: {
    "vault:holdings": {
      datasets: ["holdings"],
      map: (r) =>
        one("holdings", {
          account: ACCOUNT,
          source: r.source ?? "kite",
          snapshot_at: ist(r.snapshot_at),
          kind: r.kind,
          symbol: r.symbol,
          isin: nul(r.isin),
          quantity: Number(r.quantity),
          avg_price: Number(r.avg_price ?? 0),
        }),
    },
    "vault:trades": {
      datasets: ["trades"],
      map: (r) =>
        one("trades", {
          trade_key:
            r.trade_key ??
            `${r.source}:${r.source_ref}:${r.symbol}:${day(r.trade_date)}:${r.side}:${r.quantity}`,
          account: ACCOUNT,
          source: r.source,
          source_ref: r.source_ref ?? "",
          kind: r.kind,
          symbol: r.symbol,
          isin: nul(r.isin),
          side: r.side,
          trade_date: day(r.trade_date),
          quantity: Number(r.quantity),
          price: num(r.price),
          currency: r.currency ?? "INR",
          status: r.status ?? "confirmed",
        }),
    },
    "vault:trade_tags": {
      datasets: ["trade_tags"],
      map: (r) =>
        one("trade_tags", {
          trade_key: r.trade_key,
          placed_by: nul(r.placed_by),
          basket: nul(r.basket),
          how: nul(r.how),
        }),
    },
    "vault:kite_syncs": {
      datasets: ["kite_syncs"],
      map: (r) =>
        one("kite_syncs", {
          account: ACCOUNT,
          source: "kite",
          fetched_at: ist(r.fetched_at),
          trades: text(r.trades),
          positions: text(r.positions),
          margins: text(r.margins),
          gtts: text(r.gtts),
          changes: null,
        }),
    },
    "vault:corporate_actions": {
      datasets: ["corporate_actions"],
      map: (r) =>
        one("corporate_actions", {
          symbol: r.symbol,
          ex_date: day(r.ex_date),
          kind: r.kind,
          isin: nul(r.isin),
          numerator: Number(r.numerator),
          denominator: Number(r.denominator),
          subject: r.subject ?? "",
          source: "nse",
        }),
    },
    "vault:action_terms": {
      datasets: ["action_terms"],
      map: (r) =>
        one("action_terms", {
          symbol: r.symbol,
          ex_date: day(r.ex_date),
          kind: r.kind,
          new_isin: nul(r.new_isin),
          new_symbol: nul(r.new_symbol),
          cost_fraction: num(r.cost_fraction),
          price: num(r.price),
        }),
    },
  },
};
export default map;
