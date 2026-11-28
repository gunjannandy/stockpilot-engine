import { z } from "zod";
import { CallHistoryResponse } from "../calls/calls";
import { IstTime } from "../core/time";
import { FactsResponse } from "../facts/facts";
import { WatchlistResponse } from "../lists/lists";
import { NewsResponse, StockNewsResponse } from "../news/news";
import { HoldingsResponse } from "../portfolio/portfolio";
import { ChartResponse, StockResponse } from "../stocks/stocks";
import { TodayResponse } from "../today/today";

/** One market index (the broad ones Market and news shows at the top). A figure the source did not give is null. */
export const IndexRow = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  close: z.number().nullable(),
  change_pct: z.number().nullable(),
});
export const IndicesResponse = z.object({
  /** When the figures were taken (IST text); null while nothing has been loaded. */
  as_of: IstTime.nullable(),
  indices: z.array(IndexRow),
});
export type IndicesResponse = z.infer<typeof IndicesResponse>;

/** The one read each live screen's pane makes. `:name` in a path is filled by `routePath`. A pane reads
 * through `<Pane route=...>` (web/src/panekit), which checks the answer against `response`. */
export const screenRoutes = {
  today: { path: "/api/today", response: TodayResponse },
  holdings: { path: "/api/portfolio/holdings", response: HoldingsResponse },
  watchlist: { path: "/api/watchlist", response: WatchlistResponse },
  stock: { path: "/api/stocks/:symbol", response: StockResponse },
  stockChart: { path: "/api/stocks/:symbol/chart", response: ChartResponse },
  stockCalls: { path: "/api/calls/:symbol", response: CallHistoryResponse },
  stockFacts: { path: "/api/facts/:symbol", response: FactsResponse },
  stockNews: { path: "/api/news/stock/:symbol", response: StockNewsResponse },
  news: { path: "/api/news", response: NewsResponse },
  indices: { path: "/api/market/indices", response: IndicesResponse },
} as const;
export type ScreenRouteId = keyof typeof screenRoutes;
export type ScreenRoute = { path: string; response: z.ZodType };

export function routePath(route: Pick<ScreenRoute, "path">, params: Record<string, string> = {}) {
  return route.path.replace(/:(\w+)/g, (_, k: string) => encodeURIComponent(params[k] ?? ""));
}
