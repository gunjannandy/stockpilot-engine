# MONEY review (chapter 10)

A read of the area's money code on `main` and `area/MONEY` for wrong numbers: lots and corporate
actions, tax and harvest, the ITR pack, RSUs, XIRR, risk, USD/INR and the dividend calendar.
Files read: `money/src/{core,lots,tax,itr,rsu,xirr,risk,budget,units}`, `money/rules/tax-rules.json`,
`api/src/money/routes.ts`, `api/src/itr/routes.ts`, `api/src/lots/load.ts`, `api/src/fx/rates.ts`.

Two of the ported functions are pinned to the Python by captured checks (C-060-1 for `harvest`,
C-062-1 for `rsuView`). Where the Python is wrong, the fix is an option the routes turn on, so the
parity checks stay as they are.

## Fixed on `area/MONEY` (tests in `api/src/money/review.test.ts`, `api/src/itr/itr.test.ts`)

| # | Where | Wrong number | Fix |
|---|-------|--------------|-----|
| F1 | `GET /api/money/xirr`, `GET /api/money/risk` | Read raw trade quantities, so splits, bonuses and demergers were ignored. A 2-for-1 split stock was valued at half, which made XIRR, concentration and the Nifty −10% figure wrong. | Both read the rebuilt lots and sales. XIRR cash flows are lot cost (a bonus costs nothing, a demerged lot keeps its share of cost and date) and sale proceeds. Lots that only Kite explains have no known cash flow, so XIRR leaves them out with a warning. Risk counts them. |
| F2 | `harvest` (tax) | When a stock's oldest long-term lots netted to a loss, it was not suggested, but its loss still added to the tax-free room left, so later stocks were sized past the exemption. | Option `spendOnlySuggested`, which the tax route turns on. |
| F3 | `GET /api/money/tax` | Harvest room used the long-term gain of the year asked for, not of today's tax year. Asking for a past year gave the wrong room. | The room comes from today's tax year and its rules. |
| F4 | `rsuView`, RSU route | Long-term counted as more than 730 days. The Act counts 24 months, and the two differ by a day across a leap year. | `longTermMonths: 24`. |
| F5 | `rsuView`, RSU route | "Tax if sold" was worked out lot by lot, with no loss set-off. A short-term loss lot did not reduce long-term gain, which overstated the tax. | Option `net`: a short-term loss meets short-term gain, then long-term gain. A long-term loss meets only long-term gain. Cess is added to both rates. Surcharge depends on other income and is left out, as the comment says. |
| F6 | RSU route | Expected vests ran from the latest *still-held* vest, so selling the newest lot moved the schedule back. Vests already in the past were listed as expected. | Every documented vest counts. Only future dates are listed. |
| F7 | `GET /api/itr/pack` | Called `buildPack` with `closes: {}`, so Schedule FA peak and closing values were always blank. | Passes the stored `us_prices` closes for the calendar year. |
| F8 | `GET /api/money/calendar` | Expected date = ex-date's year + 1 as text, so 29 February gave an impossible date. | `addYears` (29 Feb becomes 1 Mar). |
| F9 | money routes | "Today" was the UTC date, which is still yesterday between 00:00 and 05:30 IST. That can shift the tax-year boundary, the long-term day and the vest filter. | `istDay`. |
| F10 | `GET /api/money/tax` | Pre-2018 equity sales silently used actual cost, because no 31 Jan 2018 value is loaded. | Warning naming the stocks, like the ITR pack's. |

## Open (not fixed; in the notebook's Next)

| # | Where | Issue | Why not fixed now |
|---|-------|-------|-------------------|
| O1 | `money/rules/tax-rules.json` | The FY 2024-25 set has FY 2025-26 slabs and rebate. FY 2024-25 actually had nil to 3L, 5% to 7L, 10% to 10L, 15% to 12L, 20% to 15L and 30% above, with the rebate up to a 7L income and a 25k cap. Equity sales before 23 Jul 2024 paid 15% short-term and 10% long-term. | C-060-1 pins the 2024 set to the Python's single rule set. The tax route now warns for FY 2024. A correct fix needs a dated split inside the year, and the captured cases need regenerating from fixed Python. |
| O2 | `realise` / `statementLots` | Fidelity's rupee cost is turned into dollars at the vest-day rate, and the tax route then turns it back at the prior-month-end rate. The RSU cost in the tax and ITR figures drifts from the perquisite value by the month's rate move. The RSU pane, which uses the vest-day rate, disagrees with the tax route. | The fix is to carry rupee cost on the lot, which changes `Lot` and the parity-pinned rebuild. |
| O3 | tax and ITR | Grandfathering never applies: no 31 Jan 2018 value is loaded. s.55(2)(ac) wants the *highest* price quoted that day, not the close. | Needs a stored source (NSE bhavcopy of 31 Jan 2018, free). |
| O4 | rebuild sales | Brokerage and charges are not carried into `TaxSale.expenses`, so gains are slightly overstated (the safe side). | The trades table has no charges column. |
| O5 | `incomeTax` | Marginal relief at the 12L rebate edge applies only to slab tax, not to tax on special-rate gains. | Matches the Python. The legal reading is unsettled. |
| O6 | calendar | Expected dividend cash uses shares held now. A split or bonus between now and the expected date is not applied. | Small. It is an estimate and labelled so. |
| O7 | XIRR | Dividends received are not cash flows, so XIRR understates the return for dividend payers. | Needs dividends paid per holding (the `dividends` table has per-share amounts, but not received cash or record-date holdings). |
| O8 | `scheduleFa` | `initial_value` takes the whole lot even when part of it was sold before the year began. | Matches the Python (C-060-1). Low impact. |
| O9 | rsuView / positions | A missing rate for a lot's day silently falls back to today's rate. | The fx Job fills from the first lot's day. A warning would be better. |

## Checked and right

- Long-term for equity: more than 12 months (sold after the same day a year later). Foreign shares: more than 24 months. Debt funds bought after 1 Apr 2023: always short-term.
- Loss set-off order: short-term loss against short-term then long-term gain, long-term loss only against long-term gain. Carried losses expire after 8 years.
- Grandfathered cost formula (s.112A): max(actual, min(FMV, sale)).
- Surcharge is capped at 15% on dividends and on 111A/112/112A gains. The 87A rebate is not set against special-rate tax.
- Splits scale quantity and cost per share and keep the date. A bonus is a new zero-cost lot dated the ex-date. A demerger splits cost by the cost fraction and keeps the parent's date.
- Schedule FA uses the calendar year (Jan–Dec) for the tax year starting that April.
- USD/INR is the nearest earlier stored rate. Weekends and holidays take the last published rate.
