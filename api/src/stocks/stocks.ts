// Stock data access: the universe (current run of the `universe` dataset), the stored history, the load Job.
import {
  type CloseRow,
  type HistoryPost,
  type UniverseRow,
  universeRowCheck,
} from "@stockpilot/contract";
import type { D1Like } from "../app";

export async function loadUniverse(d1: D1Like): Promise<UniverseRow[]> {
  const p = (await d1
    .prepare("select run_id from pointers where dataset = 'universe'")
    .first()) as { run_id: string } | null;
  if (!p) return [];
  const r = (await d1
    .prepare("select body from dataset_rows where dataset = 'universe' and run_id = ? order by seq")
    .bind(p.run_id)
    .all()) as { results: { body: string }[] };
  return r.results
    .map((x) => JSON.parse(x.body) as UniverseRow)
    .filter((u) => !universeRowCheck(u));
}

/** Search by symbol or name: symbol prefix first, then name words; delisted stocks last. Pure over the rows. */
export function searchUniverse(rows: UniverseRow[], q: string, limit = 20): UniverseRow[] {
  const needle = q.trim().toLowerCase();
  if (!needle) return [];
  const score = (u: UniverseRow) => {
    const sym = u.symbol.toLowerCase();
    const aliases = u.aliases.split("|");
    let s: number | null = null;
    if (sym === needle) s = 0;
    else if (aliases.includes(needle)) s = 1;
    else if (sym.startsWith(needle)) s = 2;
    else if (aliases.some((a) => a.startsWith(needle))) s = 3;
    else if (u.name.toLowerCase().includes(needle)) s = 4;
    return s === null
      ? null
      : s + (u.status === "delisted" ? 10 : 0) + (u.exchange === "BSE" ? 0.5 : 0);
  };
  return rows
    .map((u) => ({ u, s: score(u) }))
    .filter((x): x is { u: UniverseRow; s: number } => x.s !== null)
    .sort((a, b) => a.s - b.s || a.u.symbol.localeCompare(b.u.symbol))
    .slice(0, limit)
    .map((x) => x.u);
}

export async function findStock(d1: D1Like, symbol: string): Promise<UniverseRow | null> {
  const want = symbol.toUpperCase();
  const all = await loadUniverse(d1);
  const hits = all.filter((u) => u.symbol.toUpperCase() === want);
  return hits.find((u) => u.exchange === "NSE") ?? hits[0] ?? null;
}

export async function storeHistory(d1: D1Like, post: HistoryPost): Promise<number> {
  const stmt = d1.prepare(
    `insert into stock_history (symbol, exchange, date, open, high, low, close, prev_close, volume)
     values (?, ?, ?, ?, ?, ?, ?, ?, ?)
     on conflict(symbol, exchange, date) do update set open = excluded.open, high = excluded.high, low = excluded.low,
       close = excluded.close, prev_close = excluded.prev_close, volume = excluded.volume`,
  );
  const rows = post.rows;
  for (let i = 0; i < rows.length; i += 50)
    await d1.batch(
      rows
        .slice(i, i + 50)
        .map((r) =>
          stmt.bind(
            post.symbol,
            post.exchange,
            r.date,
            r.open,
            r.high,
            r.low,
            r.close,
            r.prev_close,
            r.volume,
          ),
        ),
    );
  return rows.length;
}

export async function readHistory(
  d1: D1Like,
  symbol: string,
  exchange: string,
  from?: string,
): Promise<CloseRow[]> {
  const r = (await d1
    .prepare(
      "select date, open, high, low, close, prev_close, volume from stock_history where symbol = ? and exchange = ? and date >= ? order by date",
    )
    .bind(symbol, exchange, from ?? "0000-00-00")
    .all()) as { results: CloseRow[] };
  return r.results;
}
