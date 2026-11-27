// C-016-1 (unit side): the shell's synced time is read from the Sync status; C-070-2: the steps run to done.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { discoverWords } from "../../areas";
import { WordsProvider } from "../../words";
import pane from "./index";
import { shortTime } from "./useSynced";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("shortTime words an IST time", () => {
  expect(shortTime("2026-11-28T09:15:00+05:30")).toBe("28 Nov, 09:15");
  expect(shortTime(null)).toBeUndefined();
});

it("the pane shows the synced time and the steps to done", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      Response.json({
        synced_at: "2026-11-28T09:15:00+05:30",
        changes: 3,
        steps: [
          { id: "login", state: "ok", count: null },
          { id: "holdings", state: "ok", count: 2 },
          { id: "trades", state: "ok", count: 1 },
          { id: "done", state: "ok", count: 3 },
        ],
      }),
    ),
  );
  const words = discoverWords(
    { "./words/sync.en.json": (await import("../../words/sync.en.json")) as never },
    "en",
  );
  const Pane = pane.Component;
  render(
    <QueryClientProvider client={new QueryClient()}>
      <WordsProvider value={words}>
        <Pane />
      </WordsProvider>
    </QueryClientProvider>,
  );
  await waitFor(() => expect(screen.getByTestId("synced-at").textContent).toBe("28 Nov, 09:15"));
  expect(screen.getByTestId("steps").textContent).toContain("Done, 3 changes");
});
