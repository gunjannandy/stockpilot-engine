// Screen checks that need no real data: every approved screen renders from its made-up or empty data,
// shows a heading, and never leaks a missing word key, in English and in Bengali.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { discoverWords } from "../areas";
import { WordsProvider } from "../words";

const mm = (q: string) =>
  ({ matches: false, media: q, addEventListener() {}, removeEventListener() {} }) as never;
window.matchMedia ??= mm;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const SCREENS = [
  "today",
  "watchlist",
  "market",
  "worth",
  "portfolio",
  "funds",
  "record",
  "feedback",
];
const modules = import.meta.glob("./*/index.tsx", { eager: true }) as Record<
  string,
  { default: { Component: React.ComponentType } }
>;
const KEY =
  /\b(?:shell|today|console|pf|stock|funds|news|worth|record|market|watchlist|admin|feedback|panes|mk|rc|v3)\.[a-z][\w.]*/;

for (const lang of ["en", "bn"] as const) {
  describe(`screens in ${lang}`, () => {
    for (const id of SCREENS) {
      it(`${id} renders a heading and no missing words`, async () => {
        vi.stubGlobal(
          "fetch",
          vi.fn(async () => Response.json({ error: "none" }, { status: 404 })),
        );
        const words = discoverWords(
          import.meta.glob("../words/*.json", { eager: true }) as never,
          lang,
        );
        const C = modules[`./${id}/index.tsx`]?.default.Component as React.ComponentType;
        const { container } = render(
          <QueryClientProvider
            client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
          >
            <WordsProvider value={words}>
              <C />
            </WordsProvider>
          </QueryClientProvider>,
        );
        await waitFor(() => expect(container.querySelector("h1, h2, h3")).not.toBeNull());
        const text = container.textContent ?? "";
        expect(text.match(KEY)?.[0]).toBeUndefined();
      });
    }
  });
}
