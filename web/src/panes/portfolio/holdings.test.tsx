// R4: Holdings renders from the API in every state, and the Sync dot shows only when the Worker says so.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { discoverWords } from "../../areas";
import { WordsProvider } from "../../words";
import { SyncDot } from "../sync/SyncDot";
import { asOfDay, callWord, Holdings } from "./Holdings";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const holding = (symbol: string, kind = "stock", source = "kite") => ({
  account: "primary",
  source,
  snapshot_at: "2026-11-26T18:00:00+05:30",
  kind,
  symbol,
  isin: null,
  quantity: 10,
  avg_price: 100,
});
const today = {
  call_line: { kind: "nothing", en: "", bn: "", symbols: [] },
  money_left_inr: null,
  market: null,
  groups: { sell: ["ALFA"], weak: [], fine_keep: [], close_to_buy: [], unusual: [] },
  as_of: null,
  stale_held: [],
};

async function view(node: React.ReactNode) {
  const words = discoverWords(
    import.meta.glob("../../words/*.json", { eager: true }) as never,
    "en",
  );
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <WordsProvider value={words}>{node}</WordsProvider>
    </QueryClientProvider>,
  );
}
const stub = (routes: Record<string, () => Response>) =>
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const hit = Object.entries(routes).find(([k]) => url.startsWith(k));
      return hit ? hit[1]() : Response.json({ error: "none" }, { status: 404 });
    }),
  );

it("words the snapshot day", () => {
  expect(asOfDay("2026-11-26T18:00:00+05:30")).toBe("Thu 26 Nov");
  expect(asOfDay(null)).toBeUndefined();
});

it("callWord finds the group of a symbol", () => {
  expect(callWord(today as never, "ALFA")).toBe("pf.call.sell");
  expect(callWord(today as never, "ZZZ")).toBeNull();
  expect(callWord(undefined, "ALFA")).toBeNull();
});

it("shows what is owned with price, gain, call and the as-of date", async () => {
  stub({
    "/api/portfolio/holdings": () =>
      Response.json({ holdings: [holding("ALFA"), holding("BETA", "mf")] }),
    "/api/quotes": () =>
      Response.json({
        quotes: [
          {
            symbol: "ALFA",
            price: 120,
            prev_close: 100,
            at: "2026-11-27T10:00:00+05:30",
            age_seconds: 5,
          },
        ],
        stale: [],
        max_age_seconds: 600,
      }),
    "/api/today": () => Response.json(today),
  });
  await view(<Holdings />);
  await waitFor(() => expect(screen.getByTestId("holdings-table")).toBeTruthy());
  expect(screen.getByTestId("holdings-asof").textContent).toContain("Thu 26 Nov");
  expect(screen.getByTestId("holdings-table").textContent).toContain("ALFA");
  // (120 - 100) * 10
  await waitFor(() => expect(screen.getByTestId("holdings-table").textContent).toContain("₹200"));
  await waitFor(() => expect(screen.getByTestId("holdings-table").textContent).toContain("Sell"));
  expect(screen.getByTestId("holdings-table").textContent).toContain("no price yet"); // the fund
});

it("still lists holdings when quotes and calls fail", async () => {
  stub({ "/api/portfolio/holdings": () => Response.json({ holdings: [holding("ALFA")] }) });
  await view(<Holdings />);
  await waitFor(() => expect(screen.getByTestId("holdings-table")).toBeTruthy());
  expect(screen.getByTestId("holdings-table").textContent).toContain("no price yet");
});

it("says so when nothing has been synced", async () => {
  stub({ "/api/portfolio/holdings": () => Response.json({ holdings: [] }) });
  await view(<Holdings />);
  await waitFor(() => expect(screen.getByTestId("holdings-empty")).toBeTruthy());
});

it("offers Try again when it fails", async () => {
  stub({});
  await view(<Holdings />);
  await waitFor(() => expect(screen.getByTestId("holdings-failed")).toBeTruthy());
});

it("the Sync dot follows the Worker's answer", async () => {
  const sync = (dot: boolean) => ({
    "/api/sync": () => Response.json({ synced_at: null, changes: null, steps: [], sync_dot: dot }),
  });
  stub(sync(true));
  const a = await view(<SyncDot />);
  await waitFor(() => expect(screen.getByTestId("sync-dot")).toBeTruthy());
  a.unmount();
  stub(sync(false));
  await view(<SyncDot />);
  await new Promise((r) => setTimeout(r, 50));
  expect(screen.queryByTestId("sync-dot")).toBeNull();
});
