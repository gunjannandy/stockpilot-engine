# v3 switch runbook

The switch makes the `stockpilotgn` Pages project (address `stockpilotgn.pages.dev`) a front door: one small function that passes every request to the v3 App (Worker `stockpilot-app`). People keep the same address, the same sign-in cookie and the same Kite redirect. Going back to v2 is one step: point the front door back at v2's last deployment.

Nothing here runs by itself. R9 does the steps on the VM. Secrets are named, never written here.

## What is in the engine

| Piece | Where |
| --- | --- |
| Front-door function (plain JS, no build) | `frontdoor/_worker.js` |
| Its tests | `api/src/auth/frontdoor.test.ts` |
| Public address for sign-in links and the same-site check | `publicOrigin` in `api/src/auth/lib.ts`, from `SITE_URL` |
| Kite login and callback | `/kite/login`, `/kite/callback` (`api/src/kite/routes.ts`) |
| Nightly backup of v3's D1 | `python -m stockpilot.jobs.backup backup` (`py/stockpilot/jobs/backup/`) |

## How the front door behaves

- Every method, path, query and body goes to `APP_ORIGIN` (default `https://stockpilot-app.stockpilotgn.workers.dev`; override with a Pages variable `APP_ORIGIN`). Redirects are never followed.
- Cookies: the session cookie is `__Host-sp`, with no `Domain`, so the browser stores it for the front-door address. The front door does not touch it.
- Redirects: the App's own are relative. A `Location` naming the App's own origin is cut down to a path; Kite's is left alone.
- Sign-in: the App builds the emailed link and checks form posts against the origin of `SITE_URL`, so `SITE_URL` must be `https://stockpilotgn.pages.dev`. Without it the link would name the Worker address.
- Kite: register `https://stockpilotgn.pages.dev/kite/callback` as the redirect URL in the Kite app settings. The callback arrives at the front door and goes through like any path.
- Known limit: the App sees the front door's address, not the visitor's, for its per-address sign-in rate limit (5 a minute); the per-email limit still holds.
- If the App is down the front door answers 502 with a short message.

## Secrets and variables, by name

Worker `stockpilot-app` (already set unless noted): `SP_PEOPLE`, `SP_COOKIE_KEY`, `GOOGLE_BRIDGE_URL`, `GOOGLE_BRIDGE_KEY`, `KITE_API_KEY`, `KITE_API_SECRET`, `GITHUB_APP_ID`, `GITHUB_INSTALLATION_ID`, `GITHUB_APP_KEY`, `CF_DEPLOY_TOKEN`; variables `SITE_URL` (set to the front-door address at the switch), `CF_ACCOUNT_ID`.
Front door (Pages): `APP_ORIGIN` only if the Worker address differs from the default.
Deploy: `CLOUDFLARE_API_TOKEN` (Pages edit), `CLOUDFLARE_ACCOUNT_ID`.
Backup workflow: `CF_ACCOUNT_ID`, `D1_PRODUCTION_ID` (the `stockpilot-v3` database id in `wrangler.toml`), `CF_D1_READ_TOKEN`, `VAULT_REMOTE`, `VAULT_KEYS` (or the keys folder), plus the ingest key the job already uses to report.

## Steps

1. **Before.** `main` is deployed and `https://stockpilot-app.stockpilotgn.workers.dev/api/health` answers. Sign in once there as the owner and press Sync to prove Kite on the Worker address.
2. **Note v2's last good deployment.** This is the rollback target.
   `pnpm wrangler pages deployment list --project-name stockpilotgn` then write down the id of the newest production deployment (the one live now).
3. **Backup v2's data** (v2's own backup, unchanged) and run the v3 backup once:
   `python -m stockpilot.jobs.backup backup`; check `GET /api/backup` shows `backup.ok` true.
4. **Set `SITE_URL`** on `stockpilot-app` to `https://stockpilotgn.pages.dev` (dashboard variable; `keep_vars` keeps it across deploys).
5. **Register the Kite redirect** `https://stockpilotgn.pages.dev/kite/callback` in the Kite app settings (keep the old one until step 9).
6. **Deploy the front door** (Direct Upload, production branch):
   `pnpm wrangler pages deploy frontdoor --project-name stockpilotgn --branch main`
   Note the new deployment id from the output.
7. **Check on the real address** `https://stockpilotgn.pages.dev`: `/login` loads; request a link, the email link starts with the front-door address; open it and sign in; `/api/me` says who you are; `/kite/login` goes to Kite and back to `/sync`; the father signs in from his phone.
8. **Turn on the nightly backup** workflow (private repo, added by the planning agent) and check the next morning's `/api/backup`.
9. **After a quiet week**, remove the old Kite redirect.

## Rollback (one step)

Point the front door back at v2's last deployment, id noted in step 2:

`curl -X POST -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/pages/projects/stockpilotgn/deployments/<V2_DEPLOYMENT_ID>/rollback`

(or Pages dashboard, project `stockpilotgn`, Deployments, that deployment, Rollback). The address is the same, so nothing else changes. Sessions signed in by v3 stop working on v2 and people sign in again with v2's link; the Kite redirect still works if v2 used the same path, otherwise re-add v2's. Data written in v3 after the switch stays in `stockpilot-v3`; the latest backup is in the vault.
