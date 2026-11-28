import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { discoverWords } from "../areas";
import { WordsProvider } from "../words";
import { Bannered, IndicesStrip } from "./index";

const words = discoverWords(
  { "./words/panes.en.json": { default: (await import("../words/panes.en.json")).default } },
  "en",
);
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
function mount(ui: React.ReactNode, answers: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (u: string) =>
      u in answers ? Response.json(answers[u]) : Response.json({}, { status: 404 }),
    ),
  );
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <WordsProvider value={words}>{ui}</WordsProvider>
    </QueryClientProvider>,
  );
}

describe("banner flags", () => {
  it("a screen not yet live shows only its banner", async () => {
    mount(<Bannered screen="funds">secret</Bannered>, { "/api/flags": { flags: {} } });
    expect(await screen.findByTestId("banner-funds")).toBeTruthy();
    expect(screen.queryByText("secret")).toBeNull();
  });
  it("the owner's switch opens it", async () => {
    mount(<Bannered screen="funds">inside</Bannered>, {
      "/api/flags": { flags: { "banner.funds": false } },
    });
    expect(await screen.findByText("inside")).toBeTruthy();
  });
  it("a bannered section leaves its neighbours alone", async () => {
    mount(
      <>
        <Bannered screen="today" section="market">
          market
        </Bannered>
        <Bannered screen="today" section="calls">
          calls
        </Bannered>
      </>,
      { "/api/flags": { flags: { "banner.today.market": true } } },
    );
    expect(await screen.findByTestId("banner-today-market")).toBeTruthy();
    expect(screen.getByText("calls")).toBeTruthy();
  });
});

describe("indices strip (the data pattern)", () => {
  it("shows the empty state for the stub's empty answer", async () => {
    mount(<IndicesStrip />, { "/api/market/indices": { as_of: null, indices: [] } });
    await waitFor(() => expect(screen.getByTestId("indices-empty")).toBeTruthy());
  });
  it("shows rows with the freshness chip", async () => {
    mount(<IndicesStrip />, {
      "/api/market/indices": {
        as_of: "2026-11-27T15:30:00+05:30",
        indices: [{ id: "a", name: "Broad", close: 1000, change_pct: 0.5 }],
      },
    });
    expect(await screen.findByText("Broad")).toBeTruthy();
    expect(screen.getByTestId("freshness")).toBeTruthy();
  });
  it("shows failed when the route fails", async () => {
    mount(<IndicesStrip />, {});
    expect(await screen.findByTestId("indices-failed")).toBeTruthy();
  });
});
