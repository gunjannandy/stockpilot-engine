// Shared and generic: never edited to add an area. Panes and words are found by folder.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  createRootRoute,
  createRoute,
  createRouter,
  Link,
  Outlet,
  RouterProvider,
  redirect,
} from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { discoverPanes, discoverWords, type Lang } from "./areas";
import { WordsProvider } from "./words";

const panes = discoverPanes(import.meta.glob("./panes/*/index.tsx", { eager: true }));
const wordFiles = import.meta.glob("./words/*.json", { eager: true }) as Record<
  string,
  { default: Record<string, string> }
>;
const lang: Lang = navigator.language.startsWith("bn") ? "bn" : "en";
const words = discoverWords(wordFiles, lang);

const root = createRootRoute({
  component: () => (
    <WordsProvider value={words}>
      <nav>
        {panes.map((p) => (
          <Link key={p.id} to={p.path}>
            {words[p.titleKey] ?? p.titleKey}
          </Link>
        ))}
      </nav>
      <Outlet />
    </WordsProvider>
  ),
});
const children = panes.map((p) =>
  createRoute({ getParentRoute: () => root, path: p.path, component: p.Component }),
);
const home = createRoute({
  getParentRoute: () => root,
  path: "/",
  beforeLoad: () => {
    if (panes[0]) throw redirect({ to: panes[0].path });
  },
});
const router = createRouter({ routeTree: root.addChildren([home, ...children]) });

createRoot(document.getElementById("root") as HTMLElement).render(
  <StrictMode>
    <QueryClientProvider client={new QueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
