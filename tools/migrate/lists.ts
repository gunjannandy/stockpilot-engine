// Lists map: v2's lists table (Worth following, In today's news) and the vault's watchlist and Not now.
// The v3 lists Job rebuilds list_rows every 30 minutes; the copy is what screens show until it first runs.
// worth_following -> top10, in_the_news -> busy_today; v2's `holdings` list is built by the browser in v3 and the
// v2 `watchlist` list is read from the vault's watchlist, so neither is copied from here. A watchlist row the owner
// removed (`removed_at`) is not carried.
import type { AreaMap } from "./core/types";
import { exchange, ist } from "./core/util";

const LIST: Record<string, string> = { worth_following: "top10", in_the_news: "busy_today" };

const map: AreaMap = {
  area: "lists",
  tables: {
    "d1:lists": {
      datasets: ["list_rows"],
      map: (r) => {
        const list = LIST[String(r.list_name)];
        if (!list || !r.symbol) return null;
        return {
          dataset: "list_rows",
          row: {
            id: `${list}:${r.symbol}`,
            list,
            symbol: String(r.symbol),
            exchange: exchange(r.exchange),
            position: Math.max(1, Math.trunc(Number(r.rank) || 1)),
            reasons_json: JSON.stringify([
              { key: "v2", en: String(r.reason ?? ""), bn: String(r.reason_bn ?? "") },
            ]),
            updated_at: ist(r.since),
          },
        };
      },
    },
    "vault:watchlist": {
      datasets: ["watchlist"],
      map: (r) => {
        if (r.removed_at) return null;
        const fund = r.kind === "fund";
        const id = String((fund ? (r.isin ?? r.symbol) : r.symbol) ?? r.id ?? "");
        if (!id) return null;
        return {
          dataset: "watchlist",
          row: {
            id,
            kind: fund ? "fund" : "stock",
            name: r.name ? String(r.name) : null,
            added_at: ist(r.added_at),
          },
        };
      },
    },
    "vault:not_now": {
      datasets: ["not_now"],
      map: (r) =>
        r.symbol
          ? {
              dataset: "not_now",
              row: {
                symbol: String(r.symbol),
                until: ist(r.until),
                created_at: ist(r.created_at ?? r.until),
              },
            }
          : null,
    },
  },
};
export default map;
