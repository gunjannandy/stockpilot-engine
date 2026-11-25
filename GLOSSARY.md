# stockpilot

A stock co-pilot that tells the owners each trading day what to buy, sell or hold in one Zerodha account, and why.

## People

**Owners**:
The account holder and his father, treated as one investor with one profile. The father is the main reader.
_Avoid_: user, client, customer

**Profile**:
The owners' facts and preferences that shape advice: goals, risk, budget, target allocation, assets outside Zerodha.
_Avoid_: settings, config

## Market

**Universe**:
Every stock stockpilot looks at on a given day: all NSE main-board stocks, plus BSE-only stocks the owners hold or watch.
_Avoid_: index, coverage

**Liquidity floor**:
The minimum average daily traded value a stock needs to enter the full screen.
_Avoid_: volume filter

**Market health**:
The day's verdict on the whole market's trend and breadth, which sets how aggressive buy calls may be.
_Avoid_: regime, sentiment

**Screen**:
The code's ranking of the universe on quality, value, momentum and risk, relative to sector.
_Avoid_: filter, scan

**Candidate**:
A stock the screen ranks high enough to go to judgement.
_Avoid_: pick, idea

**Near miss**:
A candidate that judgement did not turn into a call, shown with the reason and what would change it.

## Judgement

**Brief**:
The self-contained set of facts handed to judgement for one run.
_Avoid_: prompt, context, packet

**Fact sheet**:
One stock's entry in the brief: precomputed numbers, flags and its base rate.

**Base rate**:
How often stocks with this setup, in this market health, beat the Nifty over the horizon in the backtest.
_Avoid_: prior, historical accuracy

**Probability**:
Judgement's estimate that a stock beats the Nifty over the horizon, adjusted from its base rate.
_Avoid_: confidence, score

**Runner**:
Whichever model performs judgement on a brief.
_Avoid_: agent, LLM, bot

**Skeptic**:
A second, independent judgement that tries to knock down a borderline call.
_Avoid_: reviewer, critic

**Call**:
A dated, logged recommendation on one stock or fund: buy, add, hold, trim, sell or switch, with probability, levels and reasons.
_Avoid_: signal, prediction, tip

**Horizon**:
The period a call is judged over; positional, one to six months.

**Unproven**:
The label on calls until enough have been scored to judge the system.

**Track record**:
Every scored call and the system's hit rate and calibration. The owners see it; judgement never does.
_Avoid_: performance, history

**Job**:
One unit of work with a kind, payload, who asked, status (queued, running, done, failed), progress lines and a result summary. Every button and scheduled task is a Job; the page shows its progress. Replaces the v1 Request queue.
_Avoid_: task, request, ticket

**Ask**:
(1) An owner's question about one stock, answered by the analyst. (2) One separate wish split out of a feedback message, with its original words, a plain line in English and Bengali, a tag and a status.
_Avoid_: query, request

**News buy**:
A buy call above the model's normal adjustment limits, allowed only when a filing or two or more sources confirm a high-impact event. Labelled and scored apart.
_Avoid_: news trade, headline buy

**Change feed**:
The per-person list of decision-relevant changes (call changed, chance moved 5 points or more, list entry or exit, level crossed, asked-for forecast ready) that drives yellow dots, the tab badge and the "What changed" strip.
_Avoid_: notifications, alerts

**Starting chance**:
The mechanical forecast's chance that a stock beats the Nifty, from a smoothed base rate of similar past setups and a calibrated model. The analyst moves it only within fixed limits and explains each move.
_Avoid_: prior, score

## Portfolio

**Holding**:
A security the account owns now: a stock, a fund unit or an RSU share.
_Avoid_: position, stock

**Lot**:
One purchase of a holding, with its date, quantity and cost. Tax is worked out per lot.
_Avoid_: tranche, buy

**Snapshot**:
The holdings as Zerodha reported them at one sync.

**Sync**:
A read of the account from Zerodha, started by an owner on the dashboard.
_Avoid_: login, refresh

**Trade feed**:
Trades learned from broker emails between syncs.

**Watchlist**:
The stocks the owners want watched, edited on the dashboard. Always analysed, whatever the screen says.

**Budget**:
The money the owners can invest in a calendar month. It resets monthly.
_Avoid_: cash, balance, funds

**Target allocation**:
The mix across asset classes and market caps the owners approved, against which gaps are measured.

## Operations

**Run**:
One execution of a scheduled job, archived with its brief, calls and dashboard.

**Request**:
(v1) A job an owner asked for from a dashboard button, queued in KV. In v2 this is a **Job**.

**Tick**:
The one timed command, every 10 minutes. It answers the queue, then runs the one job that is due. A job that did not finish is due again at the next tick, which is how a late source is retried.

**Rerun**:
A request to run a job again, from the Rerun button or the doctor. It leaves a file the next tick reads; the tick runs the whole job again.

**Vault**:
The encrypted copy of all private data, kept in the repo and opened with one password.

**Self-heal**:
The chain that turns a failure into a retry, an issue, an automated fix and an Approve button.

## Funds

**Fund call**:
The weekly verdict on one held mutual fund: Keep, Add, Stop adding, Switch or Review. Never a sell order; nothing is placed.
_Avoid_: fund verdict, fund rating

**Switch (fund)**:
Selling a held fund and buying another fund in the same category. Only called when the line shows the tax, the exit load and the yearly cost saved.
_Avoid_: rebalance, churn

**Fund base rate**:
How often a fund in a given quartile of its group over 3 years stayed above its category's middle fund over the next 12 months, measured on the AMFI NAVs held, with its sample size and the average yearly cost of those funds. Absent when history is too short.
_Avoid_: persistence, hit rate

**Category middle**:
The median 12-month (or window) return of the Direct plan, Growth option funds in one AMFI category.
_Avoid_: benchmark, peer average

**SIP schedule**:
The monthly amount and day of a fund's systematic investment, read from past buys in the trades table. Absent when no pattern is found; then no amount is suggested.
_Avoid_: mandate

