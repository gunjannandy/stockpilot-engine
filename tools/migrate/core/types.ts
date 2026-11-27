// The migration tool's seams (decisions §10). A Source reads v2 (its D1 export, the KV queue, the vault
// backup); a Sink writes v3 through the ingest door; an AreaMap says how one area's v2 rows become v3 rows.
export type Row = Record<string, unknown>;
export type Kind = "d1" | "kv" | "vault";
export type Action = "copy" | "rebuild" | "drop";

/** One line of the per-table list: what happens to one v2 table, and why. */
export type Entry = {
  kind: Kind;
  table: string;
  action: Action;
  /** The area whose map (`tools/migrate/<area>.ts`) moves the rows; `copy` needs one. */
  area: string;
  reason: string;
};

export interface Source {
  /** Rows of one v2 table, streamed. A table the backup does not hold yields nothing and `has` says false. */
  rows(kind: Kind, table: string): AsyncIterable<Row>;
  has(kind: Kind, table: string): boolean;
  /** Every table the backup holds for this kind, so a table missing from the list is caught. */
  tables(kind: Kind): string[];
}

export type Written = { accepted: number; held_back: number };
export interface Sink {
  /** Does v3 have this dataset yet? A map whose target is missing is skipped and reported. */
  hasDataset(dataset: string): boolean;
  /** Insert or replace by key, so a rerun changes nothing. */
  write(dataset: string, rows: Row[]): Promise<Written>;
}

export type Mapped = { dataset: string; row: Row };
/** One v2 table's mapper: one v2 row becomes zero, one or more v3 rows, all in the datasets named. */
export type TableMap = { datasets: string[]; map: (row: Row) => Mapped | Mapped[] | null };
export type AreaMap = {
  area: string;
  /** Keyed `<kind>:<table>`, e.g. `vault:trades`. */
  tables: Record<string, TableMap>;
};
