// Shared and generic: never edited to add an area. Panes and words are found by folder.
import { QueryClientProvider } from "@tanstack/react-query";
import {
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
  redirect,
} from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { discoverPanes, discoverWords } from "./areas";
import { makeClient, persistClient } from "./cache/persist";
import { Bannered, installErrorReporting } from "./panekit";
import { morePane, Shell, samplePanes } from "./shell";
import "./shell/shell.css";
import { registerApp } from "./sw/register";
import "./theme/tokens.css";
import { applyStored, getLang } from "./theme/theme";
import { WordsProvider } from "./words";

applyStored();
// The prototype's sample screens show until each area's own pane folder replaces them.
// A real pane replaces the sample screen with the same id, in the same rail place.
const found = discoverPanes(import.meta.glob("./panes/*/index.tsx", { eager: true }));
const byId = new Map(found.map((p) => [p.id, p]));
const panes = [
  ...[...samplePanes, morePane].map((p) => byId.get(p.id) ?? p),
  ...found.filter((p) => ![...samplePanes, morePane].some((s) => s.id === p.id)),
];
const wordFiles = import.meta.glob("./words/*.json", { eager: true }) as Record<
  string,
  { default: Record<string, string> }
>;
const queryClient = makeClient();
persistClient(queryClient);
installErrorReporting();
registerApp();
const words = discoverWords(wordFiles, getLang());

const root = createRootRoute({
  component: () => (
    <WordsProvider value={words}>
      <Shell panes={panes} />
    </WordsProvider>
  ),
});
const children = panes.map((p) =>
  createRoute({
    getParentRoute: () => root,
    path: p.path,
    // Every screen sits behind its banner flag (panekit/Banner.tsx).
    component: () => (
      <Bannered screen={p.id}>
        <p.Component />
      </Bannered>
    ),
  }),
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
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
