// Writes the generated registry with a dev version: what typecheck needs to see the Worker entry.
import { repoRoot, writeGenerated } from "./discover";

writeGenerated(repoRoot);
