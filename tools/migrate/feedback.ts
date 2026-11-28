// Feedback map: v2's asks and feedback messages become v3's feedback rows. v2's read-backs and approvals
// are dropped; the owner reviews again. v2 timestamps are naive IST.
import type { AreaMap, Row } from "./core/types";

const ist = (v: unknown): string => {
  if (v === null || v === undefined || v === "") return "1970-01-01T05:30:00+05:30";
  const s = v instanceof Date ? v.toISOString() : String(v);
  if (/[zZ]|[+-]\d\d:\d\d$/.test(s)) return s;
  return `${s.replace(" ", "T").replace(/\.\d+$/, "")}+05:30`;
};
const ticket = (v: unknown) => (v === null || v === undefined || Number(v) <= 0 ? null : Number(v));
const STATUS: Record<string, string> = {
  understood: "received",
  being_built: "being_built",
  done: "done",
  declined: "not_planned",
};
const one = (row: Row) => ({ dataset: "feedback", row });

const map: AreaMap = {
  area: "feedback",
  tables: {
    "d1:asks": {
      datasets: ["feedback"],
      map: (r) =>
        one({
          id: `ask-${r.id}`,
          text: String(r.original),
          understanding: r.line_en ? String(r.line_en) : null,
          status: STATUS[String(r.status)] ?? "received",
          ticket: ticket(r.issue_number),
          stale_ticket: null,
          created_at: ist(r.updated_at),
          reviewed_at: null,
          updated_at: ist(r.updated_at),
        }),
    },
    "d1:feedback": {
      datasets: ["feedback"],
      map: (r) =>
        r.text
          ? one({
              id: `fb-${r.id}`,
              text: String(r.text),
              understanding: null,
              status: "received",
              ticket: null,
              stale_ticket: null,
              created_at: ist(r.created_at),
              reviewed_at: null,
              updated_at: ist(r.created_at),
            })
          : null,
    },
    "vault:feedback": {
      datasets: ["feedback"],
      // The same asks as d1:feedback; the d1 copy is the one moved.
      map: () => null,
    },
  },
};
export default map;
