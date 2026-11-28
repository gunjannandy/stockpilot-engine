# V3 UI handover (branch `preview/V3`, draft PR #75)

Paraphrased on purpose: no owner quotes, names, amounts or private data live in the engine.
Preview: https://v3-stockpilot-preview.stockpilotgn.workers.dev (this container cannot reach it; checks were done on a local build of the same code with the Playwright script described below).

## Intent, one line per screen
- Today: what to look at first. No money or portfolio tiles.
- Worth following: the top stocks from our analysis of thousands; no full list; fuzzy find reaches the rest.
- Stock page: chart for shape, call, facts, holding, news, similar, raw numbers table.
- Portfolio: one page of groups (Holdings, Tax, RSUs, Returns, Risk, Dividends). The All / Kite / Smallcase switch lives inside Holdings.
- Watchlist: the stocks we watch, with a glance row (close to a buy, best, weakest, need a look) and fuzzy add.
- Funds: left list in groups We own, Buy, Watch; fund page with summary cards, chart, weekly-forecast placeholder, returns, rolling, falls, cost, overlap, our buys.
- Market and news: ranked news with filter chips, sector mood, flows, coming up, exposure.
- Record: our calls against the Nifty, the owner's own trading, Smallcase vs our trades, as groups.
- Feedback: composer on the left, each ask on the right with a five-step status track.
- Admin: glance cards, then groups: Needs you, Fresh data, Job runs, Problems, Usage, Switches.
- Settings (new, lower rail): money left, monthly budget, target mix.

## Done in this pass (feedback round 1)
1. Today money and portfolio tiles gone (earlier); money left, budget and target mix now in Settings.
2. Worth following: funnel row (analysed, passed, shown) plus fuzzy find over every stock; no all-stocks switch.
3. Chart: layers are one-tap chips under the chart (also the legend); buy and sell ticks are bigger markers. Library decision in `docs/adr/0001-stock-chart-library.md` (keep Lightweight Charts).
4. Stock page: raw daily numbers table (newest first, show more, download file).
5. Portfolio rebuilt as groups with a sticky jump row; allocation strip; weight bars; row selection. Mix against target is read-only there, edited in Settings.
6. Watchlist: glance cards and fuzzy add.
7. Funds: groups, summary cards, forecast placeholder.
8. Market: filter chips, sticky side, bars that grow in.
9. Rail: Ping, Stocks, What changed, Sync hidden (earlier).
10. Record, Feedback, Admin redone.
Shared kit: `web/src/panes/_kit/` (`Group`, `GroupNav`, `Find`, `plan.ts`, kit.css motion rules). Motion: row selection, group reveal on scroll, count-up, bar grow, skeleton shimmer, hover and press states; `prefers-reduced-motion` switches it off.
MARKS: `--mark` tokens moved into `web/src/theme/tokens.css` (marks.css no longer holds colours).
Older lane branches compared with preview/V3: MARKS identical; STOCK, FUNDS, ADMIN, FEEDBACK, TODAY were rebuilt in preview/V3 and are superseded. Nothing further to take.

## Next
- Wait for the owner's feedback on the review post; apply each round the same way.
- Stock page and Today were not deepened beyond the points above (by brief).

## Decisions made (to confirm with the owner)
- Keep Lightweight Charts (ADR 0001).
- Long pages use grouped sections with a jump row, not tabs.
- Settings is a new lower-rail screen.
- Funds group "Buy / Watch" is a placeholder sample until a fund call exists.
- Yellow change mark kept as `--mark` token (owner to say whether the yellow rail mark stays).
- Verdict word: spec says "Hold", v2 says "Keep": the screens still say Keep (owner to choose).

## Needs data
- Worth following: real count of stocks analysed and count that passed our checks (two placeholder numbers in `panes/worth/index.tsx`).
- Funds: our Buy / Watch view per fund (`call`), and a weekly forecast per fund (expected NAV with range). Funds feed (`FundRow`) has costs, returns, falls and weekly NAVs only.
- Stock raw table: yearly company figures (only daily price and volume are shown).
- Watchlist: date added and move since added.
- Feedback: nothing missing; Admin: nothing missing.

## How to check
`pnpm gen`, then in `web/`: `npx vite build && npx vite preview --port 4173`; screenshot with Playwright at 1440 and 400 px, light and dark. Admin and Feedback need `/api/admin` and `/api/feedback` answers; mock them when there is no backend.

## Round 2 (owner feedback, applied)
- Stock page: daily-numbers table removed; a compact Key numbers table (range, volume, delivery, P/E, ROE, debt, growth, swing, fall, holding, results) against the sector. The pane is now a stack of separate cards, each with its own heading.
- Chart: plain text legend again; Layers is one small icon with a checkbox popover; ranges 5D, 1W, 1M, 6M, 1Y, 5Y, All; zoom is two buttons; Reset removed; Open in is two small icons (Kite, Screener); the library logo is hidden and credited in the hint line (Lightweight Charts, TradingView).
- Today: market card removed. Worth following: no cards, one-sentence heading. Watchlist: cards and add box removed.
- No in-page search bars: the top search finds any stock and has a star on each result. Preview only: it falls back to the made-up universe because there is no search index file.
- Admin: glance cards and jump row removed; switches folded under one heading (owner questions whether they are needed). Feedback: back to a v2-style box and status cards.
- Motion trimmed to DESIGN.md (opacity and colour only, nothing moves layout).
- Open: chart library swap (needs an owner decision, see review post), whether Admin switches stay, 5D and 1W look the same on daily data, the /stock page still has its own filter box.
- Lesson: read DESIGN.md and the v2/v10 shots in `docs/prototypes/v2/shots` and `legacy/web` BEFORE changing a screen; they are in the engine.

## Round 3 (applied)
- Chart: history takes 70% of the width and the forecast 30% at every range and zoom (zoom anchors on the last price). The chart was being rebuilt on every state change (unstable translate function), which reset zoom; fixed. Buy and sell markers are short (+qty, -qty) in gain/loss colour; hovering that day shows "You bought N x price = total" in the readout line.
- Logo: yellow rounded square with a trend arrow (`web/public/logo.svg`), used in the rail, the tab icon, the app icons and the theme colour.
- Rail order: Today, Watchlist, Market and news, Worth following, Portfolio, Funds; then Record, Feedback, Admin, Settings.

## Round 4 (Opus session): intent, grilling in progress
Read: this file, DESIGN.md, v2 shots, r10, legacy headers, all of `web/src` TS; current build shot at 1440 for every screen.
Owner's intent (paraphrased):
- The app is a custom market and news screener with model-made forecasts. Forecast and prediction are the most important part; Today, Watchlist and Worth following carry it.
- The current list-and-pane look is fine. The aim is to say less and show more.
- Model output (small, fast models) should be short points that move a number, a percentage or the chart, never essays.
- It must never look like an "AI dashboard"; it is an app driven by AI.
- No summary block at the top of the stock pane: prediction first, summary lower down.
- Worth following: top 10 in two groups (closest to a buy, worth watching), funnel line on top, no chips, table or screener.
- Grilling is done in written rounds in chat, not pop-up questions.
Owner's scope after round 1 (round 1 questions withdrawn):
- Tier 1, keep as is: Today, Watchlist, Worth following (only add things that make life easier).
- Tier 2, brush layout: Market and news, Portfolio, Funds.
- Tier 3, complete overhaul as working screens, not charts: Feedback, Admin, Settings, Record. Most of the running of the app (asks, jobs) is done from here.
Backend these screens can drive (already exists): GET /api/admin (needs, freshness, runs, problems, usage), POST /api/admin/retry, GET /api/admin/state + PUT release-pause, job-pause, flags, layout, POST /api/admin/recompute, POST /api/job/press (kind, subject, range, rerun), GET /api/job/run, GET /api/publish/runs and /api/publish/held/:dataset (rows held back with reasons), GET /api/secrets, GET /api/monitor (usage today), GET /api/model/status, GET/POST /api/feedback + POST /api/feedback/:id/review (owner only), GET /api/sync + POST /api/refresh (Kite), GET /api/itr/pack, GET /api/me (owner or father), GET /api/calendar/status.
Next: grilling round 2 (tier 3 layouts), then build.

## Brief for the next (Opus) session
Read all of `web/src`, `DESIGN.md`, `docs/prototypes/v2` and `docs/prototypes/ui/r10`, `legacy/web/public` and this file first. Then grill the owner about what each screen is for BEFORE designing. It may change, merge or drop anything, including layouts, keeping the existing theme (tokens, type, azure primary, graphite surfaces) and the DESIGN.md rules. Owner's direction: Portfolio, Admin and Record should be very simple. The design has hit a roadblock: aim for screens whose purpose is clear at a glance, dense and calm, cards that separate meanings, no hero blocks, one search (the top bar). Decide per screen only after reading the code and understanding the intent.
