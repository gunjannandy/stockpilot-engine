// Cloudflare entry: the same app the Node server runs, over D1. Static assets are served by the
// platform; only /api/* reaches this code (wrangler.toml run_worker_first).
import { createApp, type Env } from "./app";
import { registry, version } from "./generated/registry";

type Bindings = Env & { DB: unknown };
let app: ReturnType<typeof createApp> | undefined;

export default {
  fetch(request: Request, env: Bindings): Response | Promise<Response> {
    app ??= createApp({ d1: env.DB, env, registry, version });
    return app.fetch(request);
  },
};
