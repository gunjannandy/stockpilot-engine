import { repoRoot } from "../../api/migrate/discover";
import { scaffold } from "./scaffold";

const [name, ...flags] = process.argv.slice(2);
if (!name) {
  console.error("usage: pnpm new-area <name> [--registry]");
  process.exit(1);
}
for (const f of scaffold(repoRoot, name, { registry: flags.includes("--registry") }))
  console.log(`created ${f}`);
