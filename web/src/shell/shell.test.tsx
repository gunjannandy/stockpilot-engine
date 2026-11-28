// SHELL checks that need no real browser: C-007-1 (rail items open their screens), C-010-1 (theme survives
// a reload), C-011-1 (text size survives a reload), C-012-1 (arrows move the selection).
// The two layout checks (C-013-1 pane stays put, C-014-1 no sideways scroll) need a real browser; see the PR.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
} from "@tanstack/react-router";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { discoverWords } from "../areas";
import { applyStored } from "../theme/theme";
import { WordsProvider } from "../words";
import enWords from "../words/shell.en.json";
import { morePane, Shell, samplePanes } from "./index";

const panes = [...samplePanes, morePane];
const words = discoverWords({ "./words/shell.en.json": { default: enWords } }, "en");

async function open(path = "/today") {
  const root = createRootRoute({
    component: () => (
      <WordsProvider value={words}>
        <Shell panes={panes} />
      </WordsProvider>
    ),
  });
  const routes = panes.map((p) =>
    createRoute({ getParentRoute: () => root, path: p.path, component: p.Component }),
  );
  const router = createRouter({
    routeTree: root.addChildren(routes),
    history: createMemoryHistory({ initialEntries: [path] }),
  });
  render(
    <QueryClientProvider client={new QueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  await screen.findAllByRole("navigation");
  return router;
}

beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
  document.documentElement.removeAttribute("data-size");
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response("{}", { status: 404 })),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("C-007-1 each rail item opens its screen", () => {
  it("every rail link goes to its path and is marked current", async () => {
    const router = await open();
    const rail = screen.getAllByRole("navigation")[0] as HTMLElement;
    const links = Array.from(rail.querySelectorAll<HTMLAnchorElement>("a.nav"));
    expect(links.length).toBeGreaterThanOrEqual(8);
    for (const a of links) {
      await userEvent.click(a);
      await waitFor(() => expect(router.state.location.pathname).toBe(new URL(a.href).pathname));
      expect(a.getAttribute("aria-current")).toBe("page");
      expect(a.getAttribute("aria-label")).toBeTruthy();
    }
  });
  it("the lower group holds record, feedback and admin", async () => {
    await open();
    const rail = screen.getAllByRole("navigation")[0] as HTMLElement;
    const names = Array.from(rail.querySelectorAll("a.nav")).map((a) =>
      a.getAttribute("aria-label"),
    );
    expect(names.slice(-3)).toEqual(["Record", "Feedback", "Admin"]);
  });
});

describe("C-010-1 the theme switch survives a reload", () => {
  it("dark stays dark after a reload, and there is no Auto choice", async () => {
    await open();
    expect(screen.queryByRole("button", { name: "Auto" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Dark" }));
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    document.documentElement.removeAttribute("data-theme");
    applyStored(); // what main.tsx runs before first paint on a reload
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });
  it("an old stored 'auto' falls back to light or dark", () => {
    localStorage.setItem("sp.theme", "auto");
    applyStored();
    expect(["light", "dark"]).toContain(document.documentElement.getAttribute("data-theme"));
  });
});

describe("C-011-1 the text-size switch survives a reload", () => {
  it("A+ sets the size and keeps it after a reload", async () => {
    await open();
    await userEvent.click(screen.getByRole("button", { name: "A+" }));
    expect(document.documentElement.getAttribute("data-size")).toBe("large");
    document.documentElement.removeAttribute("data-size");
    applyStored();
    expect(document.documentElement.getAttribute("data-size")).toBe("large");
  });
});

describe("C-012-1 arrows move the selection", () => {
  it("down and up step through the list", async () => {
    await open();
    const current = () =>
      document.querySelector('.lp-row[aria-current="true"]')?.getAttribute("data-id");
    const first = current();
    await act(async () => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown" }));
    });
    const second = current();
    expect(second).not.toBe(first);
    await act(async () => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowUp" }));
    });
    expect(current()).toBe(first);
  });
});

describe("the top bar shows when Kite last synced", () => {
  it("reads the time from /api/sync", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url === "/api/sync"
          ? new Response(
              JSON.stringify({ synced_at: "2026-11-28T09:15:00+05:30", changes: 0, steps: [] }),
            )
          : new Response("{}", { status: 404 }),
      ),
    );
    await open();
    expect(await screen.findByText("Kite synced at 28 Nov, 09:15")).toBeTruthy();
  });
});
