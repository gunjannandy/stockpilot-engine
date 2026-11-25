# Site data contract (lane A)

`sp build-site` writes one JSON file per page under `site/data/`. This file lists the fields that lane A added or exports
for the first time, with a type, how often it is present and a real example. `tests/site_export/test_contract.py` builds a
site from fixtures and fails when this file and the output differ, so the UI can build on it.

## Rules every file follows
- **Dates** are ISO text (`2026-11-20`); times `2026-11-20 17:00:00`. **Money** is rupees unless the name ends `_cr` (₹ crore, 10 million). **Shares** are plain counts. **Fractions** (`change_pct`, `sales_yoy`, `probability`, `position`) are 0.05 = 5%.
- **Types** in the tables: `str`, `num`, `int`, `bool`, `list`, `obj`; `?` after a type means the key can be `null`.
- **Presence** `always`: the key is in every file of that kind (when its parent is there). `sometimes`: the key is left out when there is nothing behind it (the page hides the card; the reason belongs in the owner's Health gaps ledger, lane C). A list item (`x[]`) is `sometimes` because the list can be empty.
- **`sentence`** and every `*_note` are one plain English sentence written by fixed code rules, never by a model. They avoid trade words (no "200-day", "ASM", "stage"). Only `analyst_note` comes from the analyst, and only for stocks it wrote about.
- **`{SYMBOL}`**, **`{index}`**, **`{category}`** in a path stand for one key (a stock symbol; `nifty`, `bank`, `mid`, `small`, `vix`; `FII`, `DII`).
- **Files** are lazy: the page loads `history/<SYM>.json` and `stock/<SYM>.json` only when a stock opens. Every stock in `search.json`, plus every stock he owns, watches or has a call on, has both (about 1,617 stocks; history is about 15 KB a stock, about 25 MB in all, far under Cloudflare Pages' 25 MB per file and 20,000 files).
- **Same inputs, same bytes.** A second `sp build-site` on the same data writes identical files; only `meta.json` carries the clock (`built_at`, `built_at_utc`).

warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
## `data/history/{SYMBOL}.json`

| field | type | presence | example | meaning |
|---|---|---|---|---|
| `symbol` | str | always | `"TCS"` | NSE symbol (the file name). |
| `as_of` | str | always | `"2026-11-20"` | Date of the newest price the numbers use. |
| `dates` | list | always | `["2025-12-08", "2025-12-09"]` | Trading days, oldest first, ISO dates. |
| `dates[]` | str | sometimes | `"2025-12-08"` | One item of `dates`. |
| `close` | list | always | `[482.97, 492.03]` | Price, adjusted for splits and bonuses (₹). |
| `close[]` | num | sometimes | `482.97` | One item of `close`. |
| `volume` | list | always | `[2000000, 2000000]` | Shares traded each day, same order as `dates`. |
| `volume[]` | int | sometimes | `2000000` | One item of `volume`. |
| `dma50` | list | always | `[null, null]` | Average of the last 50 closes; null until 50 days exist. Draw as the "medium trend" line. |
| `dma50[]` | num? | sometimes | `493.52` | One item of `dma50`. |
| `dma200` | list | always | `[null, null]` | Average of the last 200 closes; null until 200 days exist. Draw as the "long trend" line. |
| `dma200[]` | num? | sometimes | `507.5` | One item of `dma200`. |
| `older` | obj | always | `{"dates": ["2025-11-14", "2025-11-21"], "close": [490.99, 481.88]}` | Longer ranges for 5Y: one point in five trading days, before the daily part. No averages. |
| `older.dates` | list | always | `["2025-11-14", "2025-11-21"]` | Dates of the weekly points, oldest first. |
| `older.dates[]` | str | sometimes | `"2025-11-14"` | One item of `older.dates`. |
| `older.close` | list | always | `[490.99, 481.88]` | Adjusted close of each weekly point. |
| `older.close[]` | num | sometimes | `490.99` | One item of `older.close`. |

## `data/stock/{SYMBOL}.json`

| field | type | presence | example | meaning |
|---|---|---|---|---|
| `symbol` | str | always | `"TCS"` | NSE symbol (the file name). |
| `name` | str | always | `"Tata Consultancy Services"` | Company name. |
| `industry` | str? | always | `"IT"` | Sector the screen groups it in; null if unknown. |
| `as_of` | str | always | `"2026-11-20"` | Date of the newest price the numbers use. |
| `close` | num | always | `532.9` | Latest adjusted close (₹). |
| `prev_close` | num | always | `522.94` | Close of the day before; null if only one day exists. |
| `change_pct` | num | always | `0.019` | Today's move as a fraction (0.012 = up 1.2%). |
| `range52` | obj | always | `{"low": 466.15, "high": 552.87, "position": 0.7697}` | Where the price sits in its last 252 trading days. |
| `range52.low` | num | always | `466.15` | Lowest close of the last year (₹). |
| `range52.high` | num | always | `552.87` | Highest close of the last year (₹). |
| `range52.position` | num | always | `0.7697` | 0 at the low, 1 at the high. |
| `range52.sentence` | str | always | `"The price is in the upper part of its 1-year range (₹466 to ₹553),..."` | One plain sentence for the block above it; fixed rules, no model. |
| `volume` | obj | always | `{"last": 2000000, "avg_20d": 2000000, "ratio": 1.0}` | Shares traded each day, same order as `dates`. |
| `volume.last` | int | always | `2000000` | Shares traded on the latest day. |
| `volume.avg_20d` | int | always | `2000000` | Average daily shares of the 20 days before; null if under 5 days. |
| `volume.ratio` | num | always | `1.0` | Latest volume over that average; 2 or more is unusual. |
| `volume.sentence` | str | always | `"Trading about as much as usual today."` | One plain sentence for the block above it; fixed rules, no model. |
| `announcements` | list | sometimes | `[{"at": "2026-11-16 12:00:00", "subject": "Interim dividend Rs 10.25 per share"}]` | Company notices to the exchange in the last 30 days, newest first, at most 8. |
| `announcements[]` | obj | sometimes | `{"at": "2026-11-16 12:00:00", "subject": "Interim dividend Rs 10.25 per share"}` | One item of `announcements`. |
| `announcements[].at` | str | sometimes | `"2026-11-16 12:00:00"` | Time announced. |
| `announcements[].subject` | str | sometimes | `"Interim dividend Rs 10.25 per share"` | What the notice says. |
| `announcements_note` | str | sometimes | `"1 company notice to the exchange in the last month."` | How many notices. |
| `analyst_note` | str | sometimes | `"Good company, but the price is not attractive yet."` | The analyst's paragraph, only on stocks the analyst wrote about in the newest run. |
| `analyst_note_bn` | str? | sometimes | `null` | Same in Kolkata Bengali; null until the run writes it. |
| `surveillance` | obj | sometimes | `{"scheme": "ASM", "stage": 2, "label": "ASM stage 2"}` | Exchange watch list entry (ASM or GSM). Absent when the stock is not on it. |
| `surveillance.scheme` | str | sometimes | `"ASM"` | ASM or GSM (never shown to the father; the sentence explains). |
| `surveillance.stage` | int | sometimes | `2` | Level number; null if the label has none. |
| `surveillance.label` | str | sometimes | `"ASM stage 2"` | The exchange's label as stored. |
| `surveillance.sentence` | str | sometimes | `"The exchange has put this stock on a short list for sharp price swi..."` | One plain sentence for the block above it; fixed rules, no model. |
| `quarters` | list | sometimes | `[{"period_end": "2024-12-31", "sales_cr": 1080.0, "profit_cr": 208.0}, {"period_end": "2025-03-31", "sales_cr": 1090.0, "profit_cr": 209.0}]` | Last eight quarters, oldest first (consolidated, else standalone; newest filing wins). |
| `quarters[]` | obj | sometimes | `{"period_end": "2024-12-31", "sales_cr": 1080.0, "profit_cr": 208.0}` | One item of `quarters`. |
| `quarters[].period_end` | str | sometimes | `"2024-12-31"` | Quarter end date. |
| `quarters[].sales_cr` | num | sometimes | `1080.0` | Sales in ₹ crore. |
| `quarters[].profit_cr` | num | sometimes | `208.0` | Net profit in ₹ crore. |
| `quarters[].sales_yoy` | num? | sometimes | `0.0385` | Sales growth on the same quarter a year before (fraction); null without it or a loss base. |
| `quarters[].profit_yoy` | num? | sometimes | `0.0196` | Profit growth on a year before (fraction); null without it or a loss base. |
| `quarters_note` | str | sometimes | `"Sales grew 801% from a year ago, and profit rose 848%."` | One plain sentence on the latest quarter. |
| `delivery` | obj | sometimes | `{"pct": 40.0, "avg_pct": 44.5, "dates": ["2026-10-12", "2026-10-13"]}` | Share of traded shares that were taken home (not sold the same day), last 60 days. |
| `delivery.pct` | num | sometimes | `40.0` | Latest day, percent. |
| `delivery.avg_pct` | num | sometimes | `44.5` | Average of the window, percent. |
| `delivery.dates` | list | sometimes | `["2026-10-12", "2026-10-13"]` | Days, oldest first. |
| `delivery.dates[]` | str | sometimes | `"2026-10-12"` | One item of `delivery.dates`. |
| `delivery.values` | list | sometimes | `[49.0, 48.0]` | Percent per day, same order. |
| `delivery.values[]` | num | sometimes | `49.0` | One item of `delivery.values`. |
| `delivery.sentence` | str | sometimes | `"40% of the shares traded were taken home, not sold again the same d..."` | One plain sentence for the block above it; fixed rules, no model. |
| `yearly` | list | sometimes | `[{"fy": "FY2023-24", "quarters": 4, "sales_cr": 4140.0}, {"fy": "FY2024-25", "quarters": 4, "sales_cr": 4300.0}]` | Up to three complete financial years (April to March), summed from four quarters each. Absent under two years. |
| `yearly[]` | obj | sometimes | `{"fy": "FY2023-24", "quarters": 4, "sales_cr": 4140.0}` | One item of `yearly`. |
| `yearly[].fy` | str | sometimes | `"FY2023-24"` | Financial year label. |
| `yearly[].quarters` | int | sometimes | `4` | Always 4: only complete years are shown. |
| `yearly[].sales_cr` | num | sometimes | `4140.0` | Summed sales, ₹ crore. |
| `yearly[].profit_cr` | num | sometimes | `814.0` | Summed net profit, ₹ crore. |
| `yearly_note` | str | sometimes | `"Yearly profit rose from ₹814 crore in FY2023-24 to ₹846 crore in FY..."` | One plain sentence on yearly profit. |
| `headlines` | list | sometimes | `[{"at": "2026-11-18 00:00:00", "title": "TCS wins a large deal", "source": "Example Wire"}, {"at": "2026-11-08 00:00:00", "title": "TCS opens a new office", "source": "Example Wire"}]` | News from the last 30 days, newest first, at most 8. |
| `headlines[]` | obj | sometimes | `{"at": "2026-11-18 00:00:00", "title": "TCS wins a large deal", "source": "Example Wire"}` | One item of `headlines`. |
| `headlines[].at` | str | sometimes | `"2026-11-18 00:00:00"` | Published time. |
| `headlines[].title` | str | sometimes | `"TCS wins a large deal"` | Headline. |
| `headlines[].source` | str | sometimes | `"Example Wire"` | Publisher. |
| `headlines[].url` | str | sometimes | `"https://example.test/2"` | Link. |
| `headlines_note` | str | sometimes | `"3 news items in the last month."` | How many news items in the last month. |
| `deals` | list | sometimes | `[{"date": "2026-11-17", "kind": "bulk", "side": "buy"}, {"date": "2026-11-10", "kind": "block", "side": "sell"}]` | Bulk and block deals in the last 30 days, newest first, at most 8. |
| `deals[]` | obj | sometimes | `{"date": "2026-11-17", "kind": "bulk", "side": "buy"}` | One item of `deals`. |
| `deals[].date` | str | sometimes | `"2026-11-17"` | Deal day. |
| `deals[].kind` | str | sometimes | `"bulk"` | bulk or block. |
| `deals[].side` | str | sometimes | `"buy"` | buy or sell. |
| `deals[].client` | str | sometimes | `"Example Fund A"` | Buyer or seller as filed. |
| `deals[].quantity` | int | sometimes | `1200000` | Shares. |
| `deals[].price` | num | sometimes | `3500.5` | ₹ per share. |
| `deals_note` | str | sometimes | `"2 large deals in the last month: 1 buying and 1 selling. Big buyers..."` | Count of buying and selling deals. |
| `results` | obj | sometimes | `{"next_on": "2026-12-10", "purpose": "Financial Results", "days_away": 20}` | Next results date from the exchange calendar. Absent when none is known. |
| `results.next_on` | str | sometimes | `"2026-12-10"` | Date. |
| `results.purpose` | str | sometimes | `"Financial Results"` | What the meeting is for. |
| `results.days_away` | int | sometimes | `20` | Days from the latest price date. |
| `results.sentence` | str | sometimes | `"Next results are expected on 10 Dec, in 20 days."` | One plain sentence for the block above it; fixed rules, no model. |
| `ownership` | obj | sometimes | `{"quarter_end": "2026-09-30", "promoter_pct": 72.0, "pledge_pct": 6.5}` | Promoter holding and pledge from the company's quarterly shareholding filing (lane D). Absent when no filing is stored or the newest quarter is over 400 days old. Filings are shown only from the day they were filed. |
| `ownership.quarter_end` | str | sometimes | `"2026-09-30"` | Quarter the filing is for. |
| `ownership.promoter_pct` | num | sometimes | `72.0` | Share of all the company's shares held by the promoter group, percent. |
| `ownership.pledge_pct` | num | sometimes | `6.5` | Share of the promoters' own shares pledged for loans, percent. Absent when the pledge could not be read (never shown as 0). |
| `ownership.change_pts` | num | sometimes | `-0.4` | Promoter holding minus the quarter before, in percentage points. Absent with only one quarter stored. |
| `ownership.trend` | list | sometimes | `[{"quarter_end": "2026-06-30", "promoter_pct": 72.4, "pledge_pct": 0.0}, {"quarter_end": "2026-09-30", "promoter_pct": 72.0, "pledge_pct": 6.5}]` | Up to five quarters, oldest first. |
| `ownership.trend[]` | obj | sometimes | `{"quarter_end": "2026-09-30", "promoter_pct": 72.0, "pledge_pct": 6.5}` | One item of `ownership.trend`. |
| `ownership.trend[].quarter_end` | str | sometimes | `"2026-09-30"` | Quarter end date. |
| `ownership.trend[].promoter_pct` | num | sometimes | `72.0` | Promoter holding, percent. |
| `ownership.trend[].pledge_pct` | num | sometimes | `6.5` | Pledged share of the promoters' shares, percent; absent when unknown. |
| `ownership.sentence` | str | sometimes | `"Promoters (the founding owners) hold 72% of the company, down 0.4 points from last quarter; 6.5% of their shares are pledged for loans."` | One plain sentence for the block above it; fixed rules, no model. |
| `reasoning` | obj | sometimes | `{"v": 1, "stance": "buy", "headline": "A cheap stock with a fair chance."}` | Why we think what we think about this stock (lane F1). Absent when there is nothing to say. Same object on `calls`, `today`, `watchlist`, `ideas` and holdings rows. A missing block is hidden, never shown as empty. |
| `reasoning.v` | int | sometimes | `1` | Version of the object. |
| `reasoning.horizon` | str | sometimes | `"about 3 months"` | How long the view is for. |
| `reasoning.stance` | str | sometimes | `"buy"` | buy, hold, watch, weak, sell, or none when there is no call. |
| `reasoning.headline` | str | sometimes | `"A cheap stock with a fair chance."` | One plain sentence he can act on (the analyst's summary, or code's when there is no call). |
| `reasoning.for` | list | sometimes | `[{"text": "Cheap at 7.8 times profit against 18.1 for its sector", "weight": 2.4, "area": "value", "by": "code"}]` | Up to five for lines, strongest first (weights are percentage points that moved the chance). |
| `reasoning.for[]` | obj | sometimes | `{"text": "Cheap at 7.8 times profit against 18.1 for its sector", "weight": 2.4, "area": "value", "by": "code"}` | One line. |
| `reasoning.for[].text` | str | sometimes | `"Cheap at 7.8 times profit against 18.1 for its sector"` | One plain sentence; every number in it comes from code or the brief. |
| `reasoning.for[].weight` | num? | sometimes | `2.4` | Percentage points it moved the chance (negative lowers it); null when the analyst gave none. |
| `reasoning.for[].area` | str | sometimes | `"value"` | trend, value, quality, growth, risk, news, owners, results, flow, sector, tax or size. |
| `reasoning.for[].by` | str | sometimes | `"code"` | code (the screen) or analyst (the model, numbers checked against the brief). |
| `reasoning.for[].asof` | str | sometimes | `"2026-11-23"` | Date the line was made. |
| `reasoning.for[].news_used` | list | sometimes | `["N1"]` | Analyst lines only: ids of the news items it rests on. |
| `reasoning.for[].news_used[]` | str | sometimes | `"N1"` | One item of `news_used`. |
| `reasoning.against` | list | sometimes | `[{"text": "Cheap at 7.8 times profit against 18.1 for its sector", "weight": -1.0, "area": "value", "by": "code"}]` | Up to five against lines, strongest first (weights are percentage points that moved the chance). |
| `reasoning.against[]` | obj | sometimes | `{"text": "Cheap at 7.8 times profit against 18.1 for its sector", "weight": -1.0, "area": "value", "by": "code"}` | One line. |
| `reasoning.against[].text` | str | sometimes | `"Cheap at 7.8 times profit against 18.1 for its sector"` | One plain sentence; every number in it comes from code or the brief. |
| `reasoning.against[].weight` | num? | sometimes | `-1.0` | Percentage points it moved the chance (negative lowers it); null when the analyst gave none. |
| `reasoning.against[].area` | str | sometimes | `"value"` | trend, value, quality, growth, risk, news, owners, results, flow, sector, tax or size. |
| `reasoning.against[].by` | str | sometimes | `"code"` | code (the screen) or analyst (the model, numbers checked against the brief). |
| `reasoning.against[].asof` | str | sometimes | `"2026-11-23"` | Date the line was made. |
| `reasoning.against[].news_used` | list | sometimes | `["N1"]` | Analyst lines only: ids of the news items it rests on. |
| `reasoning.against[].news_used[]` | str | sometimes | `"N1"` | One item of `news_used`. |
| `reasoning.facts` | list | sometimes | `[{"text": "Near the top of its 52-week range.", "area": "trend"}]` | Plain sentences from the stock file: range, volume, delivery, ownership, results date, news count. |
| `reasoning.facts[]` | obj | sometimes | `{"text": "Near the top of its 52-week range.", "area": "trend"}` | One fact. |
| `reasoning.facts[].text` | str | sometimes | `"Near the top of its 52-week range."` | The sentence. |
| `reasoning.facts[].area` | str | sometimes | `"trend"` | One of the areas above. |
| `reasoning.chance` | obj | sometimes | `{"p": 0.68, "base_rate": 0.55, "n": 3637}` | Only when a call exists. |
| `reasoning.chance.p` | num | sometimes | `0.68` | Chance it beats the Nifty by more than the hurdle over about three months. |
| `reasoning.chance.base_rate` | num | sometimes | `0.55` | Share of similar stocks that did. |
| `reasoning.chance.n` | int | sometimes | `3637` | How many past cases the base rate rests on. |
| `reasoning.chance.hurdle_pct` | num | sometimes | `2.0` | Hurdle in percent. |
| `reasoning.chance.explain` | str | sometimes | `"Out of 100 stocks like this, 68 beat the Nifty by 2% or more over three months."` | How the chance was reached, in two sentences. |
| `reasoning.levels` | obj | sometimes | `{"entry": 149.75, "stop": 135.0, "target": 164.0}` | Entry, stop and target (code's) with the reasons. |
| `reasoning.levels.entry` | num | sometimes | `149.75` | Entry (₹). |
| `reasoning.levels.stop` | num | sometimes | `135.0` | Stop (₹). |
| `reasoning.levels.target` | num | sometimes | `164.0` | Target (₹). |
| `reasoning.levels.stop_why` | str | sometimes | `"just under its recent low of \u20b9138"` | Why the stop is there. |
| `reasoning.levels.target_why` | str | sometimes | `"its recent high of \u20b9164"` | Why the target is there. |
| `reasoning.levels.target_hit_rate` | num | sometimes | `0.52` | How often similar stocks reached the target before the stop (lane F3 measures it). |
| `reasoning.levels.target_hit_n` | int | sometimes | `1800` | Cases behind `target_hit_rate`. |
| `reasoning.change_view` | list | sometimes | `[{"text": "A fall to \u20b9135 would be a sell.", "level": 135.0, "turns": "sell"}]` | What would change our view, at most five. |
| `reasoning.change_view[]` | obj | sometimes | `{"text": "A fall to \u20b9135 would be a sell.", "level": 135.0, "turns": "sell"}` | One trigger. |
| `reasoning.change_view[].text` | str | sometimes | `"A fall to \u20b9135 would be a sell."` | The trigger in plain words. |
| `reasoning.change_view[].level` | num | sometimes | `135.0` | Price level, when there is one. |
| `reasoning.change_view[].turns` | str | sometimes | `"sell"` | What it turns the call into: buy, sell or hold. |
| `reasoning.track` | obj | sometimes | `{"first_seen": "2026-11-20", "calls_made": 3}` | The call's history. |
| `reasoning.track.first_seen` | str | sometimes | `"2026-11-20"` | First day we made a call on it. |
| `reasoning.track.calls_made` | int | sometimes | `3` | Days we made a call on it. |
| `reasoning.track.previous_p` | num | sometimes | `0.6` | Chance on the run before. |
| `reasoning.track.change_reason` | str? | sometimes | `"Its chance rose from 60% to 68%."` | What changed since the run before; null when nothing did. |
| `reasoning.evidence_note` | str | sometimes | `"limited evidence"` | "limited evidence" when the base rate rests on fewer than 30 cases or on an unknown number. |

## `data/indices.json`

| field | type | presence | example | meaning |
|---|---|---|---|---|
| `{index}` | obj | sometimes | `{"name": "Nifty 50", "dates": ["2025-10-16", "2025-10-17"], "close": [21034.0, 21052.0]}` | One index line; keys are nifty, bank, mid, small, vix. |
| `{index}.name` | str | sometimes | `"Nifty 50"` | Index name as stored. |
| `{index}.dates` | list | sometimes | `["2025-10-16", "2025-10-17"]` | Trading days, oldest first (about 400 days). |
| `{index}.dates[]` | str | sometimes | `"2025-10-16"` | One item of `{index}.dates`. |
| `{index}.close` | list | sometimes | `[21034.0, 21052.0]` | Index level. |
| `{index}.close[]` | num | sometimes | `21034.0` | One item of `{index}.close`. |
| `{index}.change_1m` | num? | sometimes | `0.0154` | Change over 30 days (fraction); null without history. |
| `{index}.change_1y` | num? | sometimes | `0.2187` | Change over a year (fraction). |
| `{index}.sentence` | str | sometimes | `"Nifty 50 is up 1.5% over the last month and up 22% over the year."` | One plain sentence for the block above it; fixed rules, no model. |

## `data/flows.json`

| field | type | presence | example | meaning |
|---|---|---|---|---|
| `as_of` | str? | always | `"2026-11-20"` | Newest flow date; null when no flow is stored. |
| `days` | int | always | `6` | Trading days in the window. |
| `rows` | list | always | `[{"date": "2026-11-15", "category": "DII", "buy_cr": 1500.0}, {"date": "2026-11-15", "category": "FII", "buy_cr": 1000.0}]` | One row per day and category, last 60 days. |
| `rows[]` | obj | sometimes | `{"date": "2026-11-15", "category": "DII", "buy_cr": 1500.0}` | One item of `rows`. |
| `rows[].date` | str | sometimes | `"2026-11-15"` | Day. |
| `rows[].category` | str | sometimes | `"DII"` | FII (foreign) or DII (Indian funds). |
| `rows[].buy_cr` | num | sometimes | `1500.0` | Bought, ₹ crore. |
| `rows[].sell_cr` | num | sometimes | `1300.0` | Sold, ₹ crore. |
| `rows[].net_cr` | num | sometimes | `205.0` | Bought minus sold, ₹ crore. |
| `totals` | obj | always | `{"DII": {"buy_cr": 9000.0, "sell_cr": 7800.0, "net_cr": 1215.0}, "FII": {"buy_cr": 6000.0, "sell_cr": 7200.0, "net_cr": -1215.0}}` | Sums per category over the window. |
| `totals.{category}` | obj | always | `{"buy_cr": 9000.0, "sell_cr": 7800.0, "net_cr": 1215.0}` | Totals for one category. |
| `totals.{category}.buy_cr` | num | always | `9000.0` | ₹ crore. |
| `totals.{category}.sell_cr` | num | always | `7800.0` | ₹ crore. |
| `totals.{category}.net_cr` | num | always | `1215.0` | ₹ crore. |
| `totals.{category}.days` | int | always | `6` | Days counted. |
| `sentence` | str | always | `"Over the last 6 trading days, foreign funds sold ₹1,215 crore more..."` | One plain sentence for the block above it; fixed rules, no model. |

## `data/trades_closed.json`

| field | type | presence | example | meaning |
|---|---|---|---|---|
| `as_of` | str | always | `"2026-11-20"` | Date up to which sales count. |
| `closed` | int | always | `2` | Sales closed (a sale across several lots counts once). |
| `winners` | int | always | `1` | Sales with a gain above zero. |
| `losers` | int | always | `1` | The rest. |
| `total_gain` | num | always | `3600.0` | Sum of gains, ₹ (after the sale's costs). |
| `sentence` | str | always | `"1 of 2 closed trades made money; together they gained ₹3,600."` | One plain sentence for the block above it; fixed rules, no model. |
| `rows` | list | always | `[{"symbol": "ITC", "sold_on": "2026-05-05", "days": 120}, {"symbol": "TCS", "sold_on": "2026-03-10", "days": 424}]` | Newest sale first. Kite-placed trades only. |
| `rows[]` | obj | sometimes | `{"symbol": "ITC", "sold_on": "2026-05-05", "days": 120}` | One item of `rows`. |
| `rows[].symbol` | str | sometimes | `"ITC"` | Stock. |
| `rows[].sold_on` | str | sometimes | `"2026-05-05"` | Sale day. |
| `rows[].days` | int | sometimes | `120` | Average days held, weighted by shares. |
| `rows[].quantity` | num | sometimes | `20.0` | Shares sold. |
| `rows[].cost` | num | sometimes | `8000.0` | What the shares cost (₹). |
| `rows[].proceeds` | num | sometimes | `7600.0` | What the sale brought (₹). |
| `rows[].gain` | num | sometimes | `-400.0` | Proceeds minus cost minus costs (₹). |
| `rows[].term` | str | sometimes | `"short"` | long (over a year) or short. |

## `data/calls_outcomes.json`

| field | type | presence | example | meaning |
|---|---|---|---|---|
| `as_of` | str | always | `"2026-11-20"` | Date up to which calls count. |
| `sentence` | str | always | `"45 calls have a result. At 3 months, 58% beat the Nifty after costs..."` | One plain sentence for the block above it; fixed rules, no model. |
| `rows` | list | always | `[{"made_on": "2026-08-12", "symbol": "TCS", "action": "buy"}, {"made_on": "2026-08-09", "symbol": "INFY", "action": "watch"}]` | Every call with at least one result, newest first (cap 2000; latest call per day and stock). |
| `rows[]` | obj | sometimes | `{"made_on": "2026-08-12", "symbol": "TCS", "action": "buy"}` | One item of `rows`. |
| `rows[].made_on` | str | sometimes | `"2026-08-12"` | Day the call was made. |
| `rows[].symbol` | str | sometimes | `"TCS"` | Stock. |
| `rows[].action` | str | sometimes | `"buy"` | buy, sell, trim, hold or watch. |
| `rows[].probability` | num | sometimes | `0.65` | Chance we gave it beating the Nifty (fraction). |
| `rows[].base_rate` | num | sometimes | `0.5` | The base rate at the time. |
| `rows[].entry` | num | sometimes | `100.0` | Entry price. |
| `rows[].stop` | num | sometimes | `90.0` | Stop price. |
| `rows[].target` | num | sometimes | `120.0` | Target price. |
| `rows[].score_1m` | num | sometimes | `-0.0534` | 1 if it beat the Nifty by more than the hurdle after 1 month, else 0; null until scored. |
| `rows[].score_3m` | num | sometimes | `-0.0153` | Same at 3 months. |
| `rows[].score_6m` | num? | sometimes | `0.0141` | Same at 6 months. |
| `rows[].outcome_1m` | str | sometimes | `"missed"` | beat or missed; null until scored. |
| `rows[].outcome_3m` | str | sometimes | `"missed"` | beat or missed. |
| `rows[].outcome_6m` | str? | sometimes | `"beat"` | beat or missed. |

## `data/today.json` (partial)

| field | type | presence | example | meaning |
|---|---|---|---|---|
| `buy[].why` | str? | sometimes | `null` | The code's plain reason for the call (null when none). |
| `buy[].sell_kind` | str? | sometimes | `null` | sell, weak or review on a sell or trim call; null on every other call. Sell: its sell price was reached, the analyst says the reason for owning it broke, or the size limit. Weak: a low chance alone. Review: a holding he keeps for years (never a sell for one weak quarter). Set by the forecaster on the call. |
| `sell[].why` | str? | sometimes | `null` | The code's plain reason for the call (null when none). |
| `sell[].sell_kind` | str? | sometimes | `"weak"` | sell, weak or review on a sell or trim call; null on every other call. Sell: its sell price was reached, the analyst says the reason for owning it broke, or the size limit. Weak: a low chance alone. Review: a holding he keeps for years (never a sell for one weak quarter). Set by the forecaster on the call. |
| `watch_triggers[].sell_kind` | str? | sometimes | `null` | sell, weak or review on a sell or trim call; null on every other call. Sell: its sell price was reached, the analyst says the reason for owning it broke, or the size limit. Weak: a low chance alone. Review: a holding he keeps for years (never a sell for one weak quarter). Set by the forecaster on the call. |
| `keep[].sell_kind` | str? | sometimes | `null` | sell, weak or review on a sell or trim call; null on every other call. Sell: its sell price was reached, the analyst says the reason for owning it broke, or the size limit. Weak: a low chance alone. Review: a holding he keeps for years (never a sell for one weak quarter). Set by the forecaster on the call. |
| `not_yet[].sell_kind` | str? | sometimes | `null` | sell, weak or review on a sell or trim call; null on every other call. Sell: its sell price was reached, the analyst says the reason for owning it broke, or the size limit. Weak: a low chance alone. Review: a holding he keeps for years (never a sell for one weak quarter). Set by the forecaster on the call. |
| `since` | obj | always | `{"previous_on": "2026-11-19", "new": ["M&M", "SUNPHARMA"], "changed": [{"symbol": "WIPRO", "from": "hold", "to": "sell"}]}` | What changed against the run before. |
| `since.previous_on` | str? | always | `"2026-11-19"` | Date of that run; null on the first run. |
| `since.new` | list | always | `["M&M", "SUNPHARMA"]` | Symbols with a buy or sell call now and no call then. |
| `since.new[]` | str | sometimes | `"M&M"` | One item of `since.new`. |
| `since.changed` | list | always | `[{"symbol": "WIPRO", "from": "hold", "to": "sell"}]` | Calls whose action changed. |
| `since.changed[]` | obj | sometimes | `{"symbol": "WIPRO", "from": "hold", "to": "sell"}` | One item of `since.changed`. |
| `since.changed[].symbol` | str | sometimes | `"WIPRO"` | Stock. |
| `since.changed[].from` | str | sometimes | `"hold"` | Action then. |
| `since.changed[].to` | str | sometimes | `"sell"` | Action now. |
| `since.dropped` | list | always | `["TATASTEEL"]` | Buy or sell calls then, not buy or sell now. |
| `since.dropped[]` | str | sometimes | `"TATASTEEL"` | One item of `since.dropped`. |
| `since.moved` | list | always | `[{"symbol": "ICICIBANK", "from": 0.6, "to": 0.68}]` | Calls whose chance moved 5 points or more (not already in `changed`). |
| `since.moved[]` | obj | sometimes | `{"symbol": "ICICIBANK", "from": 0.6, "to": 0.68}` | One item of `since.moved`. |
| `since.moved[].symbol` | str | sometimes | `"ICICIBANK"` | Stock. |
| `since.moved[].from` | num | sometimes | `0.6` | Chance then. |
| `since.moved[].to` | num | sometimes | `0.68` | Chance now. |
| `since.sentence` | str | always | `"Since last time: 2 new, 1 changed, 1 dropped, 1 with a moved chance."` | One plain sentence for the strip. |
| `unusual` | list | always | `[{"symbol": "WIPRO", "name": "Wipro", "held": true}, {"symbol": "SBIN", "name": "State Bank of India", "held": false}]` | Owned, watched or called stocks with something out of the ordinary today; most signals first. |
| `unusual[]` | obj | sometimes | `{"symbol": "WIPRO", "name": "Wipro", "held": true}` | One item of `unusual`. |
| `unusual[].symbol` | str | sometimes | `"WIPRO"` | Stock. |
| `unusual[].name` | str | sometimes | `"Wipro"` | Company name. |
| `unusual[].held` | bool | sometimes | `true` | He owns it. |
| `unusual[].watchlist` | bool | sometimes | `true` | It is on the watchlist. |
| `unusual[].signals` | list | sometimes | `[{"kind": "results", "text": "Results are coming"}, {"kind": "forecast_moved", "text": "Our chance moved from 50% to 33%"}]` | What is unusual. |
| `unusual[].signals[]` | obj | sometimes | `{"kind": "results", "text": "Results are coming"}` | One item of `unusual[].signals`. |
| `unusual[].signals[].kind` | str | sometimes | `"results"` | volume, at_trend, corporate_action, results, forecast_moved or watch_list_entry. |
| `unusual[].signals[].text` | str | sometimes | `"Results are coming"` | Plain sentence for the chip. |
| `buy[].reasoning` | obj | sometimes | `{"v": 1, "stance": "buy", "headline": "A cheap stock with a fair chance."}` | The reasoning object (see `stock/{SYMBOL}`). |
| `sell[].reasoning` | obj | sometimes | `{"v": 1, "stance": "buy", "headline": "A cheap stock with a fair chance."}` | The reasoning object (see `stock/{SYMBOL}`). |
| `keep[].reasoning` | obj | sometimes | `{"v": 1, "stance": "buy", "headline": "A cheap stock with a fair chance."}` | The reasoning object (see `stock/{SYMBOL}`). |
| `not_yet[].reasoning` | obj | sometimes | `{"v": 1, "stance": "buy", "headline": "A cheap stock with a fair chance."}` | The reasoning object (see `stock/{SYMBOL}`). |

## `data/calls.json` (partial)

| field | type | presence | example | meaning |
|---|---|---|---|---|
| `buys[].sell_kind` | str? | sometimes | `null` | sell, weak or review on a sell or trim call; null on every other call. Sell: its sell price was reached, the analyst says the reason for owning it broke, or the size limit. Weak: a low chance alone. Review: a holding he keeps for years (never a sell for one weak quarter). Set by the forecaster on the call. |
| `sells[].why` | str? | sometimes | `null` | The code's plain reason for the call (null when none). |
| `sells[].sell_kind` | str | sometimes | `"weak"` | sell, weak or review on a sell or trim call; null on every other call. Sell: its sell price was reached, the analyst says the reason for owning it broke, or the size limit. Weak: a low chance alone. Review: a holding he keeps for years (never a sell for one weak quarter). Set by the forecaster on the call. |
| `follow[].sell_kind` | str? | sometimes | `null` | sell, weak or review on a sell or trim call; null on every other call. Sell: its sell price was reached, the analyst says the reason for owning it broke, or the size limit. Weak: a low chance alone. Review: a holding he keeps for years (never a sell for one weak quarter). Set by the forecaster on the call. |
| `buys[].reasoning` | obj | sometimes | `{"v": 1, "stance": "buy", "headline": "A cheap stock with a fair chance."}` | The reasoning object (see `stock/{SYMBOL}`). |
| `sells[].reasoning` | obj | sometimes | `{"v": 1, "stance": "buy", "headline": "A cheap stock with a fair chance."}` | The reasoning object (see `stock/{SYMBOL}`). |
| `follow[].reasoning` | obj | sometimes | `{"v": 1, "stance": "buy", "headline": "A cheap stock with a fair chance."}` | The reasoning object (see `stock/{SYMBOL}`). |

## `data/portfolio.json` (partial)

| field | type | presence | example | meaning |
|---|---|---|---|---|
| `holdings[].long_term` | bool | sometimes | `false` | True when the owner marked this holding "I hold this for years" (the `long_term_marks` table, lane W). The page shows the mark after a reload and judges it over years, so one weak quarter is a Review, never a Sell. |

## `data/market.json` (partial)

| field | type | presence | example | meaning |
|---|---|---|---|---|
| `flows` | obj? | always | `{"as_of": "2026-11-20", "days": 6, "totals": {"DII": {"buy_cr": 9000.0, "sell_cr": 7800.0, "net_cr": 1215.0}, "FII": {"buy_cr": 6000.0, "sell_cr": 7200.0, "net_cr": -1215.0}}}` | Fund-flow summary; null when no flow is stored. Rows are in `flows.json`. |
| `flows.as_of` | str | sometimes | `"2026-11-20"` | Newest flow date. |
| `flows.days` | int | sometimes | `6` | Trading days in the window. |
| `flows.totals` | obj | sometimes | `{"DII": {"buy_cr": 9000.0, "sell_cr": 7800.0, "net_cr": 1215.0}, "FII": {"buy_cr": 6000.0, "sell_cr": 7200.0, "net_cr": -1215.0}}` | Sums per category. |
| `flows.totals.{category}` | obj | sometimes | `{"buy_cr": 9000.0, "sell_cr": 7800.0, "net_cr": 1215.0}` | One category. |
| `flows.totals.{category}.buy_cr` | num | sometimes | `9000.0` | ₹ crore. |
| `flows.totals.{category}.sell_cr` | num | sometimes | `7800.0` | ₹ crore. |
| `flows.totals.{category}.net_cr` | num | sometimes | `1215.0` | ₹ crore. |
| `flows.totals.{category}.days` | int | sometimes | `6` | Days. |
| `flows.sentence` | str | sometimes | `"Over the last 6 trading days, foreign funds sold ₹1,215 crore more..."` | Who is buying, in one sentence. |

## The `reasoning` object (lane F1)

One object per stock, built once (`src/stockpilot/reasoning.py`) and shown identically on `calls.json` (buys, sells, follow), `today.json` cards, `watchlist.json` rows, `ideas.json` rows (ranking and near_misses; a near miss's `change_view` holds its trigger), `portfolio.json` holdings and `stock/{SYMBOL}.json`. The fields are in the `stock/{SYMBOL}` table above (`reasoning.*`). Rules: a stock with no call gets code-only lines and no `chance`; every number in a sentence comes from code or the brief; the analyst's `what_we_do_not_know` stays out of the site. A missing block is hidden by the page, never shown as "not available".

## Removed
- `market.json` `flows_note` and `watchlist.json` `bulk_deals_note` (the stale "not collected yet" lines). Flows are in `flows.json` and `market.json` `flows`; deals are in each stock file's `deals`.
- `history/<SYM>.json` is no longer limited to calls, holdings, the watchlist and the top ideas.

## Files not listed above
`meta`, `today` (the groups `buy`, `sell`, `watch_triggers`, `keep`, `not_yet`, `budget`), `market`, `ideas`, `watchlist`, `portfolio`, `record`, `health`, `lookup`, `search`, `calls`, `settings`, `feedback`, `learned`, `funds`, `smallcase`, `own_record` keep their earlier shape; the `(partial)` sections above list only what lane A added to them. Lane B adds the RSU group to `portfolio`, lane C reshapes `health`, lane D adds `ownership` to the stock files.
