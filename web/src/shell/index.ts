import type { Pane } from "../areas";
import { MorePane } from "./Shell";

export { Shell } from "./Shell";
export { samplePanes } from "./sample";
export const morePane: Pane = {
  id: "more",
  path: "/more",
  titleKey: "shell.nav.more",
  Component: MorePane,
};
