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
