// Tested against a mock of the contract: the fake server answers only what the contract allows,
// and every answer is validated by the contract's own schemas before the pane sees it.

import { routes } from "@stockpilot/contract";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { discoverWords } from "../../areas";
import { WordsProvider } from "../../words";
import pane from "./index";

function mockServer() {
  const rows: { id: string; at: string; source: "button" | "job" }[] = [];
  const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    if (url === routes.ping_press.path && method === routes.ping_press.method) {
      const row = routes.ping_press.response.parse({
        id: `p${rows.length + 1}`,
        at: "2026-11-27T10:00:00+05:30",
        source: "button",
      });
      rows.push(row);
      return Response.json(row);
    }
    if (url === routes.ping_latest.path && method === routes.ping_latest.method) {
      return Response.json(
        routes.ping_latest.response.parse({ latest: rows.at(-1) ?? null, count: rows.length }),
      );
    }
    return new Response("nope", { status: 404 });
  });
  return { fetcher, rows };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Ping pane", () => {
  it("presses Ping and shows the row it reads back", async () => {
    const { fetcher } = mockServer();
    vi.stubGlobal("fetch", fetcher);
    const words = discoverWords(
      {
        "./words/ping.en.json": {
          default: {
            title: "Ping",
            press: "Ping",
            pressing: "…",
            last: "Last ping",
            never: "No ping yet",
            count: "Pings so far",
            failed: "x",
          },
        },
      },
      "en",
    );
    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <WordsProvider value={words}>
          <pane.Component />
        </WordsProvider>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("last").textContent).toBe("No ping yet"));
    await userEvent.click(screen.getByRole("button", { name: "Ping" }));
    await waitFor(() => expect(screen.getByTestId("count").textContent).toBe("1"));
    expect(screen.getByTestId("last").textContent).toBe("2026-11-27T10:00:00+05:30");
  });
});
