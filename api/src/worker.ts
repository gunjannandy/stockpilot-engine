// Cloudflare entry: the same app the Node server runs, over D1. Static assets are served by the
// platform behind the sign-in check in auth/routes.ts (wrangler.toml run_worker_first = /*).
import { createApp, type Env } from "./app";
import { registry, version } from "./generated/registry";
import { type DutyMessage, enqueueDuties, handleBatch } from "./schedule/duties";

type Bindings = Env & {
  DB: unknown;
  DUTIES: { send(message: DutyMessage): Promise<void> };
  GITHUB_APP_ID?: string;
  GITHUB_INSTALLATION_ID?: string;
  GITHUB_APP_KEY?: string;
  SITE_URL?: string;
  CF_DEPLOY_TOKEN?: string;
  CF_ACCOUNT_ID?: string;
  CF_WORKER_NAME?: string;
};
let app: ReturnType<typeof createApp> | undefined;

export default {
  fetch(request: Request, env: Bindings): Response | Promise<Response> {
    app ??= createApp({ d1: env.DB, env, registry, version });
    return app.fetch(request);
  },
  /** Cron every 5 minutes: one queue message per due duty (schedule/duties.ts). */
  async scheduled(_event: unknown, env: Bindings): Promise<void> {
    await enqueueDuties(env.DUTIES, new Date());
  },
  /** Queue consumer, batch size 1: each duty runs in its own invocation. */
  async queue(
    batch: { messages: { body: DutyMessage; ack(): void; retry(): void }[] },
    env: Bindings,
  ): Promise<void> {
    await handleBatch(batch, {
      d1: env.DB,
      env,
      version,
      now: () => new Date(),
    });
  },
};
