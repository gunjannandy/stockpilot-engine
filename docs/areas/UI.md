# UI

Status: building

## Done
- Merged `origin/main` into `preview/V3`; conflicts only in `web/src/panes/admin/index.tsx` and `web/src/words/admin.{en,bn}.json`, resolved to the approved Admin screen (main's routes unchanged).
- `gate` blockers fixed: `web/src/panes/admin/admin.test.tsx` rewritten for the approved Admin (glance and Details); English and Bengali words files added for every pane folder (`web/src/words/{_kit,fundoverlap,market,portfolio,record,watchlist}.{en,bn}.json`). No screen look changed.
- Local: lint, typecheck, web and api tests, py tests, never-order, workflow-triggers, contract-additive, trace green.

- Baseline screenshots of ten approved screens (1440 light, 400 light, 1440 dark): `docs/prototypes/ui/baseline/`.
- Screen checks without real data: `web/src/panes/screens.test.tsx` (eight screens, English and Bengali: heading shown, no missing word keys).

## Next
- [ ] Push; confirm `gate` green on PR (privacy gate needs a secret list, cannot run here).
- [ ] Wire real routes: budget, money left, target mix (MONEY); fund calls; worth counts.
- [ ] Set Status: done when PR merged and all checks green.

## Decisions
- Admin conflict: took the approved screen; main's Admin pane was the old list and its test no longer matched.
- Words files carry only a `title` key; the screens read their words from existing files.
- Bengali keeps English call words; Admin cards only for kinds with runs or data; unheld funds keep the placeholder tag (as answered in the brief).

## Blocked
- private run: privacy gate needs PRIVACY_DENY_LIST (CI secret), cannot be run in this container.
