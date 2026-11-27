// Discovery by folder: every `tools/migrate/<area>.ts` default-exports that area's AreaMap.
import { existsSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import type { AreaMap } from "./types";

export const migrateDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");

export async function discoverMaps(dir = migrateDir): Promise<AreaMap[]> {
  if (!existsSync(dir)) return [];
  const files = readdirSync(dir, { withFileTypes: true })
    .filter(
      (f) =>
        f.isFile() &&
        f.name.endsWith(".ts") &&
        !f.name.endsWith(".test.ts") &&
        !f.name.endsWith(".d.ts"),
    )
    .map((f) => f.name)
    .sort();
  const maps: AreaMap[] = [];
  for (const f of files) {
    const mod = await import(pathToFileURL(join(dir, f)).href);
    if (mod.default?.area && mod.default?.tables) maps.push(mod.default as AreaMap);
  }
  return maps;
}
