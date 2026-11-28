// The Watchlist reads /api/watchlist and writes stars and Hide through the API; every state draws.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { discoverWords } from "../../areas";
import { WordsProvider } from "../../words";
import pane from "./index";
import { stockRows, verdictOf } from "./rows";

window.matchMedia ??= ((q: string) =>
  ({
    matches: false,
    media: q,
    addEventListener() {},
    removeEventListener() {},
  }) as never) as never;
vi.mock("../../charts/StockChart", () => ({ StockChart: () => null }));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const call = (verdict: string, chance: number | null) =>
  ({
    id: "AAA:2026-11-27:1",
    symbol: "AAA",
    exchange: "NSE",
    made_on: "2026-11-27",
    verdict,
    chance,
    horizon_days: 63,
    base_cases: 40,
    base_rate: 0.5,
    sell_line: 0.3,
    buy_line: 0.6,
    could_rise_to: null,
    would_buy_at: null,
    sell_at_once_at: null,
    limited: false,
    sentences_json: "[]",
    similar_n: 0,
    similar_beat: 0,
    model_version: "t",
    confidence: null,
  }) as never;
const item = (id: string, kind: "stock" | "fund", c: never | null = null) => ({
  id,
  kind,
  name: id.toLowerCase(),
  added_at: "2026-11-01T10:00:00+05:30",
  call: c,
});

describe("rows", () => {
  it("maps every verdict to a group", () => {
    const v = ["Sell", "Weak", "Hold", "Watch", "Buy", "Trim", "No view yet"].map((x) =>
      verdictOf(call(x, null)),
    );
    expect(v).toEqual(["sell", "weak", "keep", "watch", "buy", "weak", "watch"]);
    expect(verdictOf(null)).toBe("watch");
  });
  it("leaves funds out of the stock rows and shows a missing chance as empty", () => {
    const rows = stockRows({
      items: [item("AAA", "stock", call("Buy", 0.62)), item("BBB", "stock"), item("F1", "fund")],
      not_now: [],
    });
    expect(rows.map((r) => [r.id, r.strength])).toEqual([
      ["AAA", 62],
      ["BBB", 0],
    ]);
  });
});

function mount(answer: unknown, status = 200) {
  const fetchMock = vi.fn(async (_u: string, _i?: RequestInit) =>
    status === 200 ? Response.json(answer) : Response.json({ error: "x" }, { status }),
  );
  vi.stubGlobal("fetch", fetchMock);
  const words = discoverWords(
    import.meta.glob("../../words/*.json", { eager: true }) as never,
    "en",
  );
  const C = pane.Component;
  const view = render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <WordsProvider value={words}>
        <C />
      </WordsProvider>
    </QueryClientProvider>,
  );
  return { fetchMock, view };
}

describe("Watchlist pane", () => {
  it("says so when nothing is watched", async () => {
    mount({ items: [], not_now: [] });
    expect(await screen.findByText(/Nothing on the watchlist yet/)).toBeTruthy();
  });

  it("draws stocks, a fund and a hidden stock from the answer", async () => {
    mount({
      items: [item("AAA", "stock", call("Buy", 0.62)), item("F1", "fund"), item("CCC", "stock")],
      not_now: [
        {
          symbol: "CCC",
          until: "2026-12-20T10:00:00+05:30",
          created_at: "2026-11-20T10:00:00+05:30",
        },
      ],
    });
    expect((await screen.findAllByText("aaa")).length).toBeGreaterThan(0);
    expect(screen.getByText("f1")).toBeTruthy();
    expect(screen.getByText("ccc")).toBeTruthy(); // in Hidden for now
    expect(screen.getByText("Back from snooze")).toBeTruthy();
  });

  it("removing a star deletes it through the API", async () => {
    const { fetchMock } = mount({ items: [item("AAA", "stock", call("Buy", 0.62))], not_now: [] });
    fireEvent.click(await screen.findByLabelText("Watch this stock"));
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([u, i]) => u === "/api/watchlist/AAA" && i?.method === "DELETE"),
      ).toBe(true),
    );
  });

  it("shows the failed state with Try again", async () => {
    mount(null, 500);
    expect(await screen.findByText("Try again")).toBeTruthy();
  });
});
