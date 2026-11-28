import type { z } from "zod";
import { CalendarRow, calendarRowCheck } from "./calendar/calendar";
import { CallsRun, SCREEN_MIN, ScreenRow } from "./calls/calls";
import type { JobKind } from "./core/jobs";
import { PingRow } from "./core/ping";
import { FACTS_MIN, FactsRow, factsRowCheck } from "./facts/facts";
import { FeedbackRow } from "./feedback/feedback";
import { FUND_CALLS_MIN, FundCallRow, fundCallRowCheck } from "./fundcalls/fundcalls";
import {
  FUND_HOLDINGS_MIN,
  FundHoldingsRow,
  fundHoldingsRowCheck,
} from "./fundholdings/fundholdings";
import { FUNDS_MIN, FundRow, fundRowCheck } from "./funds/funds";
import { RawTrade } from "./kite/kite";
import { LISTS_MIN_TOP, ListRow, listRowCheck } from "./lists/lists";
import { DividendsRun, UsPricesRun } from "./money/money";
import { NewsItemRow } from "./news/news";
import { RecordRun } from "./record/record";
import { HistoryRun, UniverseRow, universeRowCheck } from "./stocks/stocks";
import { MarketRow, marketRowCheck } from "./today/today";

/** One line per dataset (decisions §2 Publishing). Python validates rows against `row`'s generated
 * JSON Schema; the door enforces `writeBudget` per day. */
export type Dataset = {
  /** Registry key, also the ingest door's `dataset` value. */
  name: string;
  /** The Job that produces it. */
  job: JobKind;
  table: string;
  /** Plain-words schedule. */
  schedule: string;
  /** How stale it may get before health turns amber. */
  freshnessHours: number;
  /** Data checks: a row check holds a row back; a run check fails the run. */
  checks: { row: string[]; run: string[] };
  /** `private` datasets (holdings, trades, tax, feedback) never leave the owner's store: previews fill them with made-up rows only. Every registry entry states it (checks/C-203-1 fails otherwise). */
  visibility?: "public" | "private";
  recomputable: boolean;
  /** Most D1 rows this dataset may write in a day (a row costs 1 + its indexes). */
  writeBudget: number;
  row: z.ZodType;
  /** `rows` (default, up to 1,000 per run) or `file`: one content-hashed file per run, only its pointer and summary in D1. */
  delivery?: "rows" | "file";
  /** Extra row check beyond `row`'s schema: a reason holds the row back and the run goes on. */
  rowCheck?: (row: Record<string, unknown>) => string | null;
  /** Run check: a reason fails the run. `rows` is present for `rows` delivery only. */
  runCheck?: (run: {
    rowCount: number;
    rows?: Record<string, unknown>[];
    summary: Record<string, unknown>;
  }) => string | null;
  /** Most rows one run may publish as rows when the default (ROWS_LIMIT) is too small: the screens read these rows from D1 (the universe, the facts), so they cannot be a file. Never above `writeBudget`. */
  rowsLimit?: number;
  /** Share of a run's rows that may be held back before the run fails (default 0.2). */
  heldBackLimit?: number;
  /** When the 5-minute tick starts this dataset's Job: from `at` (IST, HH:MM) on every day, or only on trading days. Absent: only by a press. */
  run?: { at: string; on: "trading" | "every" };
};

export const datasets = {
  ping: {
    name: "ping",
    job: "ping",
    table: "ping",
    schedule: "on press, and when the Ping Job runs",
    freshnessHours: 24 * 365,
    checks: { row: ["id is not empty", "at is IST"], run: [] },
    visibility: "public",
    recomputable: false,
    writeBudget: 200,
    row: PingRow,
  },
  documents: {
    name: "documents",
    job: "documents",
    table: "document_trades",
    schedule: "on Refresh, and when the Documents Job runs",
    freshnessHours: 24 * 365,
    checks: { row: ["account and source are present", "date is a date"], run: [] },
    visibility: "private",
    recomputable: false,
    writeBudget: 1000,
    row: RawTrade,
  },
  calendar: {
    name: "calendar",
    job: "calendar",
    table: "calendar",
    schedule: "every morning at 07:00 IST",
    freshnessHours: 48,
    checks: { row: ["kind is known", "date is a date"], run: ["at least one holiday listed"] },
    visibility: "public",
    recomputable: true,
    writeBudget: 1000,
    row: CalendarRow,
    rowCheck: calendarRowCheck,
    run: { at: "07:00", on: "every" },
    runCheck: (run) =>
      (run.rows ?? []).some((r) => r.kind === "holiday") ? null : "no holiday listed",
  },
  funds: {
    name: "funds",
    job: "funds",
    table: "funds",
    schedule: "every night at 21:00 IST",
    freshnessHours: 72,
    checks: { row: ["at least two NAVs", "costs are not negative"], run: ["at least 100 funds"] },
    visibility: "private",
    recomputable: true,
    writeBudget: 1000,
    row: FundRow,
    rowCheck: fundRowCheck,
    run: { at: "21:00", on: "every" },
    runCheck: (run) => (run.rowCount < FUNDS_MIN ? "fewer than 100 funds" : null),
  },
  fund_calls: {
    name: "fund_calls",
    job: "funds",
    table: "fund_calls",
    schedule: "every night at 21:00 IST, with the funds it is built from",
    freshnessHours: 72,
    checks: {
      row: ["a call row has a call", "a chance has its cases"],
      run: ["at least 5 rows"],
    },
    visibility: "private",
    recomputable: true,
    writeBudget: 1000,
    row: FundCallRow,
    rowCheck: fundCallRowCheck,
    run: { at: "21:00", on: "every" },
    runCheck: (run) => (run.rowCount < FUND_CALLS_MIN ? "fewer than 5 rows" : null),
  },
  fund_holdings: {
    name: "fund_holdings",
    job: "fundholdings",
    table: "fund_holdings",
    schedule:
      "every night at 22:00 IST (houses publish monthly; a night with nothing new republishes the same month)",
    freshnessHours: 24 * 45,
    checks: { row: ["at least one holding"], run: ["at least 20 funds"] },
    visibility: "private",
    recomputable: true,
    writeBudget: 1000,
    row: FundHoldingsRow,
    rowCheck: fundHoldingsRowCheck,
    run: { at: "22:00", on: "every" },
    runCheck: (run) => (run.rowCount < FUND_HOLDINGS_MIN ? "fewer than 20 funds" : null),
  },
  facts: {
    name: "facts",
    job: "facts",
    table: "facts",
    schedule: "every Sunday at 03:00 IST",
    freshnessHours: 24 * 9,
    checks: {
      row: ["symbol is present", "at least one raw figure", "every sentence has Bengali"],
      run: ["at least 100 stocks"],
    },
    visibility: "public",
    recomputable: true,
    writeBudget: 5000,
    rowsLimit: 5000,
    row: FactsRow,
    rowCheck: factsRowCheck,
    run: { at: "03:00", on: "every" },
    runCheck: (run) => (run.rowCount < FACTS_MIN ? "fewer than 100 stocks" : null),
  },
  screen: {
    name: "screen",
    job: "screen",
    table: "screen_runs",
    schedule: "every trading day at 22:30 IST",
    freshnessHours: 72,
    checks: { row: [], run: ["at least 100 stocks"] },
    visibility: "public",
    recomputable: true,
    writeBudget: 10,
    row: ScreenRow,
    delivery: "file",
    run: { at: "22:30", on: "trading" },
    runCheck: (run) => (run.rowCount < SCREEN_MIN ? "fewer than 100 stocks" : null),
  },
  calls_runs: {
    name: "calls_runs",
    job: "forecast",
    table: "calls_runs",
    schedule: "every trading day at 23:00 IST",
    freshnessHours: 72,
    checks: { row: ["id is not empty"], run: [] },
    visibility: "public",
    recomputable: true,
    writeBudget: 10,
    row: CallsRun,
    run: { at: "23:00", on: "trading" },
  },
  lists: {
    name: "lists",
    job: "lists",
    table: "list_rows",
    schedule: "every 30 minutes in market hours, and after the nightly screen",
    freshnessHours: 72,
    checks: {
      row: ["every row has a reason", "every reason has Bengali"],
      run: ["the Top 10 list has 10 stocks"],
    },
    visibility: "public",
    recomputable: true,
    writeBudget: 4000,
    row: ListRow,
    rowCheck: listRowCheck,
    runCheck: (run) =>
      (run.rows ?? []).filter((r) => r.list === "top10").length < LISTS_MIN_TOP
        ? "the Top 10 list has fewer than 10 stocks"
        : null,
  },
  record_runs: {
    name: "record_runs",
    job: "record",
    table: "record_runs",
    schedule: "every trading day at 23:30 IST",
    freshnessHours: 72,
    checks: { row: ["id is not empty"], run: [] },
    visibility: "public",
    recomputable: true,
    writeBudget: 10,
    row: RecordRun,
    run: { at: "23:30", on: "trading" },
  },
  market: {
    name: "market",
    job: "market",
    table: "market_health",
    schedule: "every trading day at 22:00 IST",
    freshnessHours: 72,
    checks: { row: ["at least one figure", "every sentence has Bengali"], run: [] },
    visibility: "public",
    recomputable: true,
    writeBudget: 10,
    row: MarketRow,
    rowCheck: marketRowCheck,
    run: { at: "22:00", on: "trading" },
  },
  dividends: {
    name: "dividends",
    job: "dividends",
    table: "dividends_runs",
    schedule: "every day at 06:45 IST",
    freshnessHours: 72,
    checks: { row: ["id is not empty"], run: [] },
    visibility: "public",
    recomputable: true,
    writeBudget: 700,
    row: DividendsRun,
    run: { at: "06:45", on: "every" },
  },
  usprices: {
    name: "usprices",
    job: "usprices",
    table: "usprices_runs",
    schedule: "every day at 06:30 IST",
    freshnessHours: 72,
    checks: { row: ["id is not empty"], run: [] },
    visibility: "public",
    recomputable: true,
    writeBudget: 300,
    row: UsPricesRun,
    run: { at: "06:30", on: "every" },
  },
  news_items: {
    name: "news_items",
    job: "news",
    table: "news_items",
    schedule: "every 15 minutes, all day",
    freshnessHours: 2,
    checks: { row: ["id, link and title are present"], run: [] },
    visibility: "public",
    recomputable: true,
    writeBudget: 6000,
    row: NewsItemRow,
  },
  history: {
    name: "history",
    job: "history",
    table: "history_runs",
    schedule: "every trading day at 21:00 IST",
    freshnessHours: 96,
    checks: { row: ["id is not empty"], run: [] },
    visibility: "public",
    recomputable: true,
    writeBudget: 50,
    row: HistoryRun,
    run: { at: "21:00", on: "trading" },
  },
  universe: {
    name: "universe",
    job: "universe",
    table: "universe",
    schedule: "every morning at 07:30 IST",
    freshnessHours: 48,
    checks: {
      row: ["symbol and name are present"],
      run: ["at least 1,500 NSE stocks listed"],
    },
    visibility: "public",
    recomputable: true,
    writeBudget: 30000,
    rowsLimit: 12000,
    row: UniverseRow,
    rowCheck: universeRowCheck,
    run: { at: "07:30", on: "every" },
    runCheck: (run) =>
      (run.rows ?? []).filter((r) => r.exchange === "NSE" && r.status === "listed").length >= 1500
        ? null
        : "fewer than 1,500 NSE stocks listed",
  },
  feedback: {
    name: "feedback",
    // Written by the Worker's Feedback box; only the one-time v2 migration posts rows through the door.
    job: "sync",
    table: "feedback",
    schedule: "on every ask in the Feedback box; the v2 asks come in once, by the migration",
    freshnessHours: 24 * 365,
    checks: { row: ["text is not empty", "status is known"], run: [] },
    visibility: "private",
    recomputable: false,
    writeBudget: 500,
    row: FeedbackRow,
  },
} as const satisfies Record<string, Dataset>;
export type DatasetName = keyof typeof datasets;
