# Design

Mode: **Operate**. Scanability, consistency and density outrank expression. The brand lives in precise details. Compact density in the style of Seline Analytics; v8/v9 look kept: graphite surfaces, azure primary, calm.

## Tokens
Light and dark both ship; dark follows the system, a toggle in Settings overrides. All colours are tokens; no raw hex in components.

| Role | Light | Dark |
|---|---|---|
| bg | #F2F4F8 | #090C11 |
| surface | #FFFFFF | #10141B |
| container 1/2/3 | #F7F9FC / #EBEFF5 / #DEE4EE | #13181F / #192029 / #232B37 |
| text / text-2 | #0B1220 / #3B4556 | #EEF2F8 / #A9B4C6 |
| line / line-2 | #C7CFDC / #E3E8EF | #323C4C / #1F2733 |
| primary | #0B57D0 | #8AB4FF |
| selected row | primary 11% over surface | primary 14% over surface |
| gain / loss / warn | #0A7A3D / #C42525 / #8F5600 | #3DD68C / #FF6B6B / #FFB547 |
| hold / watch | #3B4556 / #0B57D0 | #C7D0DE / #8AB4FF |

Verdict words are the engine's call words, in English in both languages (market terms the owners use): **Sell** = loss, **Trim** = warn, **Buy** / **Add** = gain, **Hold** = hold, **Watch** (a list label, not a call) = watch. Funds use the fund call words: Keep, Add, Stop adding, Switch, Review. Always the word beside the colour.

Change mark: amber (`--mark`) means one thing only, "changed since you last looked": a small dot before the name, one soft glow when it first shows, the change as numbers (`Hold→Sell`, `44→34%`). No thick yellow edges or bands.

## Type
Google Sans Flex, falling back to Noto Sans Bengali then system-ui. Body 14 px / 20 px; table cells 13 px; numbers tabular and right-aligned; page title 22 px; section title 15 px semibold; small note 12 px. Minimum text 12 px on desktop, 13 px on phone. Fonts preloaded with `font-display: optional` so loading never reflows.

## Space and shape
4-px grid. Card padding 24 px on desktop, 16 px on phone. List row 44 px tall (touch-safe) with a density toggle to 36 px. Radius 12 px cards, 8 px controls, 999 px chips. One-pixel lines, shadow only for the open search menu.

## Layout
- Left rail 240 px (collapses to icons at 1100, to a bottom bar of five at 400). Top bar 64 px with search (`/`), language and theme.
- **List-and-pane** on Today, Holdings, Worth following, Watchlist, Ideas: list about 40%, pane about 60%. The list has a filter bar above it, compact colour-coded rows, sticky group headers on Today (Sell, Weak, Buy, Keep) that never collapse. The pane is dense (chart, volume, key numbers, our view, risks), the first row is pre-selected so the pane is never empty, the pane never changes size, one URL per stock so Back works, arrow keys step the list, "Open full page" for the long view. On phone: list, then the full page.
- Tools-tabs (Market and news, Record, Feedback, Admin) are workbenches of cards on a 12-column grid, reused card vocabulary. Admin is a console: at a glance, cards (running jobs, asks on a board, a grid of job cards), never tables; a Details part holds the filterable lists. The same glance is the morning email. There is no Settings screen: the monthly budget and target mix live on Portfolio; language, theme and text size in the top bar.

## Components
Row, chip, verdict badge, stat tile (number, plain sentence), chart card (title, plain sentence under it, range buttons 1M 3M 6M 1Y 5Y, toggles for averages, volume, levels, hover readout), range bar, freshness bar, change dot, EN tag (marks an untranslated sentence), empty state (never shown to the father for missing data; hide the card instead).

## Motion
Motion that never shifts layout. Allowed: colour and opacity fades; entrance fade with a rise of at most 6 px (transform), staggered up to 40 ms per item; numbers counting up; bars filling (scaleX); chart lines drawing in; running-job bars moving; a one-time amber glow on a changed row; hover lift of 1 to 2 px with a soft shadow on clickable cards. 150 to 400 ms ease-out, nothing loops except work in progress. No spring on lists. Cumulative layout shift rules below still hold. Reduced motion removes all.

## Stability rules (testable)
- Cumulative layout shift at most 0.02 on every page at 1440, 1100 and 400.
- Every chart, image and card has reserved width and height before data arrives; skeletons match the final size.
- Hover, focus and selection change colour or outline only, never size.
- No area inside the page scrolls on its own, except the list column on list-and-pane screens.
- One scroll direction on phone.

## Bans
Cards inside cards, icon-only buttons without a label, modals and floating sheets for primary data, jargon without a plain sentence, spinners that resize content, truncated numbers.
