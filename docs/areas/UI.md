# UI

Status: building

## Done
- Merged `origin/main` into `preview/V3`; conflicts only in `web/src/panes/admin/index.tsx` and `web/src/words/admin.{en,bn}.json`, resolved to the approved Admin screen (main's routes unchanged).
- `gate` blockers fixed: `web/src/panes/admin/admin.test.tsx` rewritten for the approved Admin (glance and Details); English and Bengali words files added for every pane folder (`web/src/words/{_kit,fundoverlap,market,portfolio,record,watchlist}.{en,bn}.json`). No screen look changed.
- Local: lint, typecheck, web and api tests, py tests, never-order, workflow-triggers, contract-additive, trace green.

- Baseline screenshots of ten approved screens (1440 light, 400 light, 1440 dark): `docs/prototypes/ui/baseline/`.
- Screen checks without real data: `web/src/panes/screens.test.tsx` (eight screens, English and Bengali: heading shown, no missing word keys).
- Portfolio budget and money left read `GET /api/portfolio/settings` and `/trades`, budget saves with `PUT /api/portfolio/budget` (`web/src/panes/portfolio/index.tsx`, helpers and tests in `web/src/panes/_kit/plan.ts`). Made-up numbers stay where a route does not answer (preview, father).

- Chapter 3: merged `origin/main` again; `ts` job fixed: `web/src/panes/screens.test.tsx` stubs the canvas chart (jsdom has no canvas) and the media-query mock has the old listener methods, so no unhandled errors fail the run. Lint, typecheck, web and api tests green locally.

## Next
- [ ] Push; confirm `gate` green on PR (privacy gate needs a secret list, cannot run here).
- [ ] Target mix: route mix is by asset class (stocks, equity_funds, ...), screen's is by sector; wire without changing the look (needs a mapping decision).
- [ ] Fund calls from `GET /api/fund-calls`; worth counts; other made-up screens to real routes.
- [ ] Set Status: done when PR merged and all checks green.

## Decisions
- Mix left made-up for now: the route's classes differ from the sector rows on the approved card.
- Admin conflict: took the approved screen; main's Admin pane was the old list and its test no longer matched.
- Words files carry only a `title` key; the screens read their words from existing files.
- Bengali keeps English call words; Admin cards only for kinds with runs or data; unheld funds keep the placeholder tag (as answered in the brief).

## Blocked
- private run: privacy gate needs PRIVACY_DENY_LIST (CI secret), cannot be run in this container.

Chapter end: 3
