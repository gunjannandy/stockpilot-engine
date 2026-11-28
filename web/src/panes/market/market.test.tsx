// Market and news from the API: cards by time with their stocks, and every state of the news pane.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { discoverWords } from "../../areas";
import { WordsProvider } from "../../words";
import pane, { byTime, istParts } from "./index";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const impact = (item_id: string, over: Record<string, unknown> = {}) => ({
  id: `${item_id}:AAA`,
  item_id,
  symbol: "AAA",
  exchange: "NSE",
  relation: "self",
  direction: "good",
  size: "large",
  sector_only: false,
  why_en: "Wins an order.",
  why_bn: "অর্ডার পেয়েছে।",
  weight: 2,
  judged_at: "2026-11-27T10:00:00+05:30",
  ...over,
});
const item = (id: string, at: string, impacts: unknown[] = []) => ({
  id,
  link: `https://example.test/${id}`,
  title: `Story ${id}`,
  source: "Wire",
  published_at: at,
  source_count: 1,
  weight: 2,
  impacts,
});

function answer(news: () => Response) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      String(url).includes("/api/news")
        ? news()
        : String(url).includes("/api/market/indices")
          ? Response.json({ as_of: null, indices: [] })
          : Response.json({ flags: {} }),
    ),
  );
}

function show(lang: "en" | "bn" = "en") {
  const words = discoverWords(
    import.meta.glob("../../words/*.json", { eager: true }) as never,
    lang,
  );
  const C = pane.Component;
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <WordsProvider value={words}>
        <C />
      </WordsProvider>
    </QueryClientProvider>,
  );
}

describe("market news", () => {
  it("orders by time, newest first, and keeps an unreadable time last", () => {
    const got = byTime([
      item("old", "2026-11-26T08:00:00+05:30"),
      item("bad", "not a time"),
      item("new", "2026-11-27T09:00:00+05:30"),
    ] as never);
    expect(got.map((c) => c.id)).toEqual(["new", "old", "bad"]);
    expect(istParts("2026-11-27T03:30:00Z")?.stamp).toBe("2026-11-27T09:00:00+05:30");
  });

  it("draws cards with the stocks each touches, and the sector-only mark", async () => {
    answer(() =>
      Response.json({
        items: [
          item("a", "2026-11-27T09:10:00+05:30", [
            impact("a"),
            impact("a", {
              id: "a:BBB",
              symbol: "BBB",
              sector_only: true,
              direction: null,
              relation: "sector",
            }),
          ]),
          item("b", "2026-11-27T08:10:00+05:30"),
        ],
      }),
    );
    show();
    await waitFor(() => expect(screen.getAllByTestId("news-card")).toHaveLength(2));
    const cards = screen.getAllByTestId("news-card");
    expect(cards[0]?.textContent).toContain("Story a");
    expect(cards[0]?.textContent).toContain("AAA");
    expect(cards[0]?.textContent).toContain("Wins an order.");
    expect(cards[0]?.textContent).toContain("Sector news");
    expect(cards[1]?.textContent).not.toContain("AAA");
  });

  it("shows the Bengali reason in Bengali", async () => {
    answer(() => Response.json({ items: [item("a", "2026-11-27T09:10:00+05:30", [impact("a")])] }));
    show("bn");
    await waitFor(() =>
      expect(screen.getByTestId("news-card").textContent).toContain("অর্ডার পেয়েছে।"),
    );
  });

  it("says so when there is no news, and when it cannot load", async () => {
    answer(() => Response.json({ items: [] }));
    show();
    await waitFor(() => expect(screen.getByTestId("news-empty")).toBeTruthy());
    cleanup();
    answer(() => Response.json({ error: "x" }, { status: 500 }));
    show();
    await waitFor(() => expect(screen.getByTestId("news-failed")).toBeTruthy());
  });

  it("the three later sections answer plainly, each under its own banner flag", async () => {
    answer(() => Response.json({ items: [] }));
    show();
    await waitFor(() => expect(screen.getByTestId("market-sector-empty")).toBeTruthy());
    expect(screen.getByTestId("market-funds-empty")).toBeTruthy();
    expect(screen.getByTestId("market-exposure-empty")).toBeTruthy();
    cleanup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        String(url).includes("/api/flags")
          ? Response.json({ flags: { "banner.market.funds": true } })
          : Response.json({ items: [], as_of: null, indices: [] }),
      ),
    );
    show();
    await waitFor(() => expect(screen.getByTestId("banner-market-funds")).toBeTruthy());
    expect(screen.queryByTestId("market-funds-empty")).toBeNull();
  });
});
