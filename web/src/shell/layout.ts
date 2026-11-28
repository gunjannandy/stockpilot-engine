// The rail draws from the layout row. Default layout = every area's pane in folder order;
// the D1 row (api/src/layout) may reorder or hide screens. Unknown ids in the row are ignored.
import type { Pane } from "../areas";

export type LayoutRow = { rail: string[]; hidden?: string[] };
/** Screens that exist as routes but never sit in the rail. */
const NEVER_IN_RAIL = new Set(["signin", "more", "ping", "sync", "changes", "stock", "itr"]);

/** v10's lower group: desk, feedback and admin screens sit at the bottom of the rail. */
const LOWER = new Set(["record", "feedback", "admin", "health"]);
export const splitRail = (items: Pane[]) => ({
  daily: items.filter((p) => !LOWER.has(p.id)),
  lower: items.filter((p) => LOWER.has(p.id)),
});

export function railItems(panes: Pane[], row: LayoutRow | null): Pane[] {
  const drawable = panes.filter((p) => !NEVER_IN_RAIL.has(p.id));
  if (!row) return drawable;
  const hidden = new Set(row.hidden ?? []);
  const byId = new Map(drawable.map((p) => [p.id, p]));
  const ordered = row.rail.flatMap((id) => {
    const p = byId.get(id);
    byId.delete(id);
    return p ? [p] : [];
  });
  return [...ordered, ...byId.values()].filter((p) => !hidden.has(p.id));
}

export async function fetchLayout(): Promise<LayoutRow | null> {
  try {
    const r = await fetch("/api/layout");
    if (!r.ok) return null;
    const j = (await r.json()) as { layout: LayoutRow | null };
    return j.layout && Array.isArray(j.layout.rail) ? j.layout : null;
  } catch {
    return null;
  }
}
