# Worker settings for deploy watching

The duties read these from the Worker environment (`platformFromEnv`, `storePromises`).

| Name | Kind | Where it is set | Purpose |
| --- | --- | --- | --- |
| `CF_DEPLOY_TOKEN` | secret | dashboard (`wrangler secret put`) | API token that may roll the Worker back |
| `CF_ACCOUNT_ID` | variable | dashboard | Cloudflare account that owns the Worker |
| `CF_WORKER_NAME` | variable | `wrangler.toml` `[vars]` | Worker to roll back (default `stockpilot-app`) |
| `SITE_URL` | variable | dashboard | Public address of the site, for store promises |

Rollback needs both `CF_DEPLOY_TOKEN` and `CF_ACCOUNT_ID`; without either, the duty runs with no platform and skips rollback.
Never put the token in git. Preview (`wrangler.preview.toml`) leaves all four unset on purpose.
