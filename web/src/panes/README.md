# Wiring a pane to real data (copy `panekit/IndicesStrip.tsx`)

1. Read through the contract: `<Pane<TodayResponse> route={screenRoutes.today} params={{ symbol }} …>` from `web/src/panekit`. The path comes from `contract/src/screens/screens.ts`; the answer is checked against its schema. Add a route there only if the screen has none.
2. Give `updatedAt` (the dataset's IST time; for a day-only `as_of`, pass `${day}T15:30:00+05:30`) and `windowHours`; the chip turns amber past the window. Never invent a time.
3. `Pane` draws loading, empty (`isEmpty`), stale (last answer kept, refresh failed), failed (with Try again) and the calm "updating" state. Do not hand-roll these.
4. Every number gets its plain sentence: use `NumberSlot`, and the shared formatters in `web/src/format.ts` (`money`, `lakh`, `pct`).
5. Words go in your area's `web/src/words/<area>.en.json` and `.bn.json`; English shows where Bengali is missing.
6. The whole screen sits behind `banner.<id>` (the router does it). Put a part of a screen under its own flag with `<Bannered screen="today" section="market">…</Bannered>` and switch it in Admin, Screens.
7. No sample data: a pane with nothing to show says so. `web/src/panes/_kit/pending.ts` holds empty stand-ins for the old sample lists; delete each import as you wire it, and delete the file when none remain.
8. Touch only your pane folder, your words files, and your own route's contract/API files.
