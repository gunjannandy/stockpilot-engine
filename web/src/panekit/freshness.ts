// The freshness chip's words come from the dataset's updated time (IST text) and its window.
export type Freshness = { stale: boolean; label: { key: string; vars: Record<string, string> } };

const IST = "+05:30";
const toMs = (t: string) => Date.parse(t.endsWith(IST) ? t : `${t}${IST}`);

export function freshness(
  updatedAt: string | null | undefined,
  windowHours: number,
  now: Date,
): Freshness {
  if (!updatedAt || Number.isNaN(toMs(updatedAt)))
    return { stale: true, label: { key: "panes.fresh.never", vars: {} } };
  const at = toMs(updatedAt);
  const mins = Math.max(0, Math.round((now.getTime() - at) / 60000));
  const stale = mins > windowHours * 60;
  const hhmm = updatedAt.slice(11, 16);
  const day = updatedAt.slice(0, 10);
  const today = new Date(now.getTime() + 5.5 * 3600000).toISOString().slice(0, 10);
  if (mins < 2) return { stale, label: { key: "panes.fresh.now", vars: {} } };
  if (day === today) return { stale, label: { key: "panes.fresh.today", vars: { time: hhmm } } };
  return { stale, label: { key: "panes.fresh.on", vars: { day, time: hhmm } } };
}

export const fill = (text: string, vars: Record<string, string>) =>
  text.replace(/\{(\w+)\}/g, (_, k: string) => vars[k] ?? "");
