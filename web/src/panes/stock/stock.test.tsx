import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { discoverWords } from "../../areas";
import { WordsProvider } from "../../words";
import { barsOfChart, pickCall, StockDetail, verdictKey } from "./StockDetail";

vi.mock("../../charts/StockChart", () => ({ StockChart: () => <div data-testid="chart" /> }));
window.matchMedia ??= (() => ({
  matches: false,
  addEventListener() {},
  removeEventListener() {},
})) as never;
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const call = (o: Record<string, unknown>) => ({
  id: "X:1",
  symbol: "DEMO",
  exchange: "NSE",
  made_on: "2026-11-27",
  verdict: "Hold",
  chance: 0.62,
  horizon_days: 63,
  base_cases: 40,
  base_rate: 0.55,
  sell_line: 0.4,
  buy_line: 0.7,
  could_rise_to: 120,
  would_buy_at: 90,
  sell_at_once_at: 80,
  limited: false,
  sentences_json: JSON.stringify([{ key: "why", en: "Earnings are steady.", bn: "আয় স্থির।" }]),
  similar_n: 24,
  similar_beat: 15,
  model_version: "m1",
  confidence: { en: "Our last 24 calls like this: 15 beat the Nifty.", bn: "বাংলা" },
  ...o,
});

function serve(routes: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const hit = Object.entries(routes).find(([p]) => String(url).endsWith(p));
      return hit ? Response.json(hit[1]) : Response.json({ error: "none" }, { status: 404 });
    }),
  );
}
function show() {
  const words = discoverWords(
    import.meta.glob("../../words/*.json", { eager: true }) as never,
    "en",
  );
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <WordsProvider value={words}>
        <StockDetail symbol="demo" />
      </WordsProvider>
    </QueryClientProvider>,
  );
}

describe("stock pane", () => {
  it("draws every section from the API", async () => {
    serve({
      "/api/stocks/DEMO": {
        symbol: "DEMO",
        known: true,
        entry: {
          symbol: "DEMO",
          exchange: "NSE",
          segment: "NSE",
          name: "Demo Ltd",
          status: "listed",
          isin: "",
        },
        last: {
          date: "2026-11-27",
          open: 1,
          high: 1,
          low: 1,
          close: 100,
          prev_close: 98,
          volume: 1,
        },
        history: { days: 2, first: "2026-11-26", last: "2026-11-27" },
        quote: null,
        load: null,
      },
      "/api/stocks/DEMO/chart": {
        symbol: "DEMO",
        d: ["2026-11-26", "2026-11-27"],
        o: [null, 99],
        h: [null, 101],
        l: [null, 98],
        c: [98, 100],
        v: [null, 5],
        ma2: [null, null],
        ma10: [null, null],
      },
      "/api/calls/DEMO": { symbol: "DEMO", calls: [call({})] },
      "/api/facts/DEMO": { as_of: "2026-11-20", facts: null },
      "/api/news/stock/DEMO": {
        symbol: "DEMO",
        news: [
          {
            id: "n1",
            link: "https://example.com/a",
            title: "Demo wins order",
            source: "wire",
            published_at: "2026-11-27T09:00:00+05:30",
            source_count: 1,
            weight: 2,
            impact: {
              id: "n1:DEMO",
              item_id: "n1",
              symbol: "DEMO",
              exchange: "NSE",
              relation: "self",
              direction: "good",
              size: "small",
              sector_only: false,
              why_en: "A new order.",
              why_bn: "নতুন অর্ডার।",
              weight: 2,
              judged_at: "2026-11-27T10:00:00+05:30",
            },
          },
        ],
      },
    });
    show();
    await screen.findByText("Demo Ltd");
    await screen.findByTestId("chart");
    expect((await screen.findByTestId("stock-call-why")).textContent).toContain(
      "Earnings are steady.",
    );
    expect(await screen.findByText("Demo wins order")).toBeTruthy();
    await screen.findByText("A new order.", { exact: false });
    // Facts have none yet: an empty state, not an error.
    await waitFor(() => expect(screen.getByTestId("stock-facts-empty")).toBeTruthy());
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows empty states, not errors, for a stock with no history and no call", async () => {
    serve({
      "/api/stocks/NEW": {
        symbol: "NEW",
        known: false,
        entry: null,
        last: null,
        history: { days: 0, first: null, last: null },
        quote: null,
        load: null,
      },
      "/api/stocks/NEW/chart": {
        symbol: "NEW",
        d: [],
        o: [],
        h: [],
        l: [],
        c: [],
        v: [],
        ma2: [],
        ma10: [],
      },
      "/api/calls/NEW": { symbol: "NEW", calls: [] },
      "/api/facts/NEW": { as_of: null, facts: null },
      "/api/news/stock/NEW": { symbol: "NEW", news: [] },
    });
    const words = discoverWords(
      import.meta.glob("../../words/*.json", { eager: true }) as never,
      "en",
    );
    render(
      <QueryClientProvider client={new QueryClient()}>
        <WordsProvider value={words}>
          <StockDetail symbol="new" />
        </WordsProvider>
      </QueryClientProvider>,
    );
    await screen.findByTestId("stock-chart-none");
    await screen.findByTestId("stock-call-none");
    await screen.findByTestId("stock-facts-empty");
    await screen.findByTestId("stock-news-empty");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("one failing read does not blank the others", async () => {
    serve({ "/api/news/stock/DEMO": { symbol: "DEMO", news: [] } });
    show();
    await screen.findByTestId("stock-news-empty");
    await screen.findByTestId("stock-chart-failed");
  });
});

describe("helpers", () => {
  it("maps verdicts and picks the newest, shortest call", () => {
    expect(verdictKey("Hold")).toBe("keep");
    expect(verdictKey("Trim")).toBe("weak");
    expect(verdictKey("No view yet")).toBeNull();
    const a = call({ made_on: "2026-11-26", horizon_days: 63 });
    const b = call({ horizon_days: 126 });
    const c = call({ horizon_days: 63 });
    expect(pickCall([a, b, c] as never)).toBe(c);
    expect(pickCall([])).toBeNull();
  });
  it("fills a missing open, high or low from the close", () => {
    const b = barsOfChart({
      symbol: "X",
      d: ["2026-01-01"],
      o: [null],
      h: [null],
      l: [null],
      c: [5],
      v: [null],
      ma2: [null],
      ma10: [null],
    });
    expect(b[0]).toMatchObject({ open: 5, high: 5, low: 5, close: 5, volume: 0 });
  });
});
