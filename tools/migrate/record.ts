// Record map: v2's archived days, "I hold this for years" marks and Smallcase orders. Each keeps its whole v2
// row as JSON text beside its key, so nothing is lost; the scores themselves are made again by the record Job.
import type { AreaMap, Row } from "./core/types";
import { dayOf, ist } from "./core/util";

const json = (r: Row) => JSON.stringify(r, (_k, v) => (typeof v === "bigint" ? Number(v) : v));

const map: AreaMap = {
  area: "record",
  tables: {
    "vault:archived_days": {
      datasets: ["archived_days"],
      map: (r) => {
        const day = dayOf(r.day ?? r.date ?? r.archived_on);
        return /^\d{4}-\d{2}-\d{2}$/.test(day)
          ? { dataset: "archived_days", row: { day, payload: json(r) } }
          : null;
      },
    },
    "vault:long_term_marks": {
      datasets: ["long_term_marks"],
      map: (r) =>
        r.symbol
          ? {
              dataset: "long_term_marks",
              row: {
                symbol: String(r.symbol),
                marked_at: ist(r.marked_at ?? r.created_at ?? r.at),
                payload: json(r),
              },
            }
          : null,
    },
    "vault:smallcase_orders": {
      datasets: ["smallcase_orders"],
      map: (r) => {
        const key = r.order_key ?? r.order_id ?? r.id;
        return key === undefined || key === null || key === ""
          ? null
          : {
              dataset: "smallcase_orders",
              row: {
                order_key: String(key),
                placed_at: ist(r.placed_at ?? r.created_at ?? r.at),
                payload: json(r),
              },
            };
      },
    },
  },
};
export default map;
