// Discovery by folder: a new area drops its folders in and touches no shared file.
import type { FunctionComponent } from "react";

export type Pane = {
  id: string;
  path: string;
  /** Words key in the area's words file for the rail label. */
  titleKey: string;
  Component: FunctionComponent;
};

export type Words = Record<string, string>;
export type Lang = "en" | "bn";

/** Every `web/src/panes/<area>/index.tsx` default-exports a Pane. */
export function discoverPanes(modules: Record<string, { default: Pane }>): Pane[] {
  return Object.entries(modules)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([, m]) => m.default);
}

/** Every `web/src/words/<area>.<lang>.json` is a flat key->text map; keys are namespaced by area. */
export function discoverWords(modules: Record<string, { default: Words }>, lang: Lang): Words {
  const out: Words = {};
  for (const [file, m] of Object.entries(modules)) {
    const name = file.split("/").pop() ?? "";
    if (!name.endsWith(`.${lang}.json`)) continue;
    const area = name.slice(0, -`.${lang}.json`.length);
    for (const [k, v] of Object.entries(m.default)) out[`${area}.${k}`] = v;
  }
  return out;
}
