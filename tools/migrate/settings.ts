// Settings map: v2's monthly budgets and target mix become v3's owner-only money_budgets and money_mix rows.
// A budget is one row per month; a mix is the JSON of the newest approval, one row per asset class.
import type { AreaMap } from "./core/types";

const AT = "1970-01-01T05:30:00+05:30";
const CLASSES = new Set(["stocks", "equity_funds", "debt_funds", "gold", "foreign", "other_funds"]);

const map: AreaMap = {
  area: "settings",
  tables: {
    "vault:budgets": {
      datasets: ["money_budgets"],
      map: (r) =>
        /^\d{4}-\d{2}$/.test(String(r.month)) && Number.isFinite(Number(r.amount_inr))
          ? {
              dataset: "money_budgets",
              row: { month: String(r.month), amount_inr: Number(r.amount_inr), updated_at: AT },
            }
          : null,
    },
    "vault:target_allocations": {
      datasets: ["money_mix"],
      map: (r) => {
        let a: unknown = r.allocation;
        if (typeof a === "string") {
          try {
            a = JSON.parse(a);
          } catch {
            return null;
          }
        }
        if (!a || typeof a !== "object") return null;
        const rows = Object.entries(a as Record<string, unknown>)
          .filter(([k, v]) => CLASSES.has(k) && Number.isFinite(Number(v)))
          .map(([k, v]) => ({
            dataset: "money_mix",
            row: { asset_class: k, share: Number(v), updated_at: AT },
          }));
        return rows.length ? rows : null;
      },
    },
  },
};
export default map;
