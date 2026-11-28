import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { discoverWords } from "../../areas";
import { WordsProvider } from "../../words";
import { TodayScreen } from "./index";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const base = {
  call_line: { kind: "sell", en: "Sell AAA first.", bn: "আগে AAA বিক্রি করুন।", symbols: ["AAA"] },
  money_left_inr: 12000,
  market: null,
  groups: { sell: ["AAA"], weak: [], fine_keep: ["BBB"], close_to_buy: [], unusual: [] },
  as_of: "2026-11-27",
  stale_held: ["CCC"],
};

function show(today: unknown, flags: Record<string, boolean> = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (u: string) =>
      String(u).includes("/api/flags")
        ? Response.json({ flags })
        : String(u).includes("/api/today")
          ? Response.json(today)
          : Response.json({}, { status: 404 }),
    ),
  );
  const words = discoverWords(
    import.meta.glob("../../words/*.json", { eager: true }) as never,
    "en",
  );
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <WordsProvider value={words}>
        <TodayScreen />
      </WordsProvider>
    </QueryClientProvider>,
  );
}

describe("Today", () => {
  it("draws the call line, calls, money left and stale holdings from the API", async () => {
    show(base);
    await waitFor(() =>
      expect(screen.getByTestId("today-line").textContent).toBe("Sell AAA first."),
    );
    expect(screen.getByTestId("today-calls").textContent).toContain("BBB");
    expect(screen.getByTestId("today-stale").textContent).toContain("CCC");
    expect(screen.getByTestId("today-money").textContent).toContain("12,000");
  });
  it("says so when there is no budget and puts a bannered section behind its banner", async () => {
    show({ ...base, money_left_inr: null }, { "banner.today.market": true });
    await waitFor(() =>
      expect(screen.getByTestId("today-money").textContent).toContain("No budget"),
    );
    await waitFor(() => expect(screen.getByTestId("banner-today-market")).toBeTruthy());
  });
  it("shows the empty state when nothing came back from the API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ error: "x" }, { status: 500 })),
    );
    const words = discoverWords(
      import.meta.glob("../../words/*.json", { eager: true }) as never,
      "en",
    );
    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <WordsProvider value={words}>
          <TodayScreen />
        </WordsProvider>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("today-failed")).toBeTruthy(), { timeout: 3000 });
  });
});
