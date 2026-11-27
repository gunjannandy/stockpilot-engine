import { readFileSync } from "node:fs";
import { join } from "node:path";
import { type Plugin, transformWithEsbuild } from "vite";

const source = join(__dirname, "src/sw/worker.ts");

/** Turns src/sw/worker.ts into plain JavaScript, as the text of /sw.js. */
export async function compileWorker(): Promise<string> {
  const { code } = await transformWithEsbuild(readFileSync(source, "utf8"), source, {
    target: "es2020",
    minify: false,
  });
  return code;
}

/** Serves the worker at /sw.js in dev and writes it to the built site. No copy lives in git. */
export function serviceWorker(): Plugin {
  return {
    name: "stockpilot-sw",
    configureServer(server) {
      server.middlewares.use("/sw.js", async (_req, res) => {
        res.setHeader("content-type", "text/javascript");
        res.setHeader("cache-control", "no-cache");
        res.end(await compileWorker());
      });
    },
    async generateBundle() {
      this.emitFile({ type: "asset", fileName: "sw.js", source: await compileWorker() });
    },
  };
}
