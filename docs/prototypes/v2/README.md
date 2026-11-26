# v2 UI prototype (ticket T4, issue #30), round 2

`prototype.html` is built by `python3 build.py` from the **deployed r10 stylesheet** (`../ui/r10/app.css`), `addon.css` (new pieces only) and `app.js` (emits the r10 markup: rail, topbar, `.lp` list and pane, `.lrow`, `.chip`, `.cb` chance bar, `.pc` chart classes). Fixture data only, invented names and numbers.
Checks: `NODE_PATH=/opt/node-tools/node_modules node docs/prototypes/v2/check.mjs` (`SHOTS=1` rewrites `shots/`).

## Owner's verdict on round 1 and the answer
- Did not match the deployed theme: rebuilt on the real stylesheet and markup.
- List 30%, detail 70%, no "Open full page": the detail pane holds the whole stock (chart with 50 and 200 day averages, volume, levels, forecast bands and buys; forecast form; P/E vs sector and own history, P/B, yield, size, sales and profit growth, ROE, ROCE, debt, promoter holding and pledge, volume vs usual, delivery %, 52-week range, results date, holding with tax note, news). The same component is the full page, used on phone and from search.
- Screener is not a page: it is the **Table** view of Worth following, with filter chips and a scope switch (Worth following / Every stock).
- Market and news: each card shows the 3 affected stocks as small tiles with a chart and call; a right column; ranking by a visible score with reason chips (you hold it, filing, sources, age, touches a call).
- Jobs rebuilt in the deployed style: summary tiles, running jobs with step trails, recent table, Try again.
- Feedback: one box, no tags; each ask shows its job and progress; "Not what I meant". Sending creates a job that shows on Jobs.
- Icon A chosen by the owner; it is now the brand mark, the favicon and the Settings preview (16 and 32 px, light and dark).

## Round 4 (feedback and answers)
- v10 controls drawn in and working on fixtures: language button (EN/বাংলা; model sentences show an EN tag), real stars (filled in the Watchlist, add and remove with Undo, counts), Hide for 30 days and Never show with Undo, verdict filter chips, list filter, List/Table on every list page.
- List rows: no percentage. A small price line and a Strong / Fair / Weak meter (colour and word). List column is 38%.
- The "Changed" band and the list bar are a neutral surface with a yellow edge and dot, readable in both themes.
- Chart zoom: plain scroll never zooms; Ctrl or Cmd + scroll, + / − buttons and Reset do. 1Y is highlighted by default.
- Build plan (spec, issue #24): the real screens are built on top of v10's code; this prototype is only the drawing.
Defects found in round 4: acts row buttons overlapped (a clashing `.star` class), "Full view" label printed its template text, Layers menu opened over the list when the toolbar wrapped, list names truncated (column widened).

## Round 3 (owner's feedback and his answers to the grilling)
- Nav restored from v10: Watchlist (own picks) and Worth following (Ideas and watch-out merged into two groups, "Closest to a buy" and "Watch out for"); Tax, Trading record and Our record are back as stubs.
- "What changed" and Mark all seen moved into the list column; the detail pane gets the full height.
- Detail pane: open sections with an icon, a bold heading and one plain sentence each, hairlines between them, no cards and no tabs. Order: header, chart, forecast, numbers, holding, news.
- Chart: range buttons plus one Layers menu; y labels in a left gutter, lighter fill, larger axis text.
- News: source name beside each title; the top "Your stocks in the news" is a wrapping grid, no sideways scroll.
- Feedback: "Not what I meant" removed; each ask has a Delete button (hidden with Undo for 8 seconds); more white space.
Defects found in round 3: icon font list must be sorted (broke icons); `.ask` class clashed with the deployed one (blue box); changes bar text wrapped in the narrow list; rail overflowed at 1100 px (now scrolls).

## Defects found in the self-audit and fixed (round 2)
1. Material Symbols subset missing the new icons (sync, savings, open_in_full): added.
2. Stock page forecast and numbers columns overlapped: column padding and grid fixed.
3. Yellow count made "Worth following" truncate in the rail: smaller pill.
4. Market tile top bars drew curved arcs: removed; helps and hurts are coloured words.
5. Nifty line overlapped its caption in the side panel: sized.
6. Chart month labels collided at 1100 px: three labels when narrow, "Dec ’25" form.
7. Phone: search placeholder cut off, Sync button too wide: shorter text.
8. Heading said "12 stocks" over a list of 5: counted from the data.
9. A lone "All 5" chip on Today served nothing: removed.
Not in the prototype: Bengali, N8 beyond the red count on Health, real Holdings, Funds and Health screens (stubs).
