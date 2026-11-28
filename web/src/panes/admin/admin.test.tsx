// C-099-1 (unit side): Admin sections render; Try again requeues a failed Job. C-106-2: Problems lists stored errors.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { discoverWords } from "../../areas";
import { WordsProvider } from "../../words";
import pane from "./index";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const overview = {
  at: "2026-11-28T09:00:00+05:30",
  needs_you: [{ id: "n1", text: "Kite login", kind: "dependency" }],
  freshness: [
    {
      dataset: "history",
      job: "history",
      schedule: "daily",
      updated_at: null,
      window_hours: 30,
      state: "never",
    },
  ],
  runs: [
    {
      key: "history:all:2026-11-28",
      kind: "history",
      day: "2026-11-28",
      status: "failed",
      attempts: 1,
      started_at: null,
      finished_at: null,
      error: "boom",
      trail: [{ at: null, text: "step one" }],
    },
  ],
  problems: [
    { id: "e1", at: "2026-11-28T08:00:00+05:30", message: "it broke", pane: "sync", url: null },
  ],
  usage: [{ screen: "sync", button: "press", n: 3 }],
};

async function mount(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const words = discoverWords(
    import.meta.glob("../../words/*.en.json", { eager: true }) as never,
    "en",
  );
  const C = pane.Component;
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <WordsProvider value={words}>
        <C />
      </WordsProvider>
    </QueryClientProvider>,
  );
}

it("details list problems and usage", async () => {
  const fetchMock = vi.fn(async (url: string) => {
    if (url === "/api/admin") return Response.json(overview);
    if (url === "/api/admin/state")
      return Response.json({ release_paused: false, paused_kinds: [], flags: {}, layout: null });
    return Response.json({ ok: true });
  });
  await mount(fetchMock);
  await screen.findByText("Kite login");
  fireEvent.click(screen.getByRole("tab", { name: "Details" }));
  fireEvent.click(await screen.findByRole("button", { name: /Page errors/ }));
  expect((await screen.findByTestId("admin-problems")).textContent).toContain("it broke");
});

it("renders the sections and Try again posts the failed Job's key", async () => {
  const fetchMock = vi.fn(async (url: string) => {
    if (url === "/api/admin") return Response.json(overview);
    if (url === "/api/admin/state")
      return Response.json({ release_paused: false, paused_kinds: [], flags: {}, layout: null });
    return Response.json({ ok: true });
  });
  await mount(fetchMock);
  await screen.findByText("Kite login");
  expect(screen.getByTestId("admin-needs").textContent).toContain("Kite login");
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/admin/retry",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ key: "history:all:2026-11-28" }),
      }),
    ),
  );
});
