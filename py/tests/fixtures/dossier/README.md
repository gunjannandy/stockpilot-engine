Real samples captured from the VM on 2026-11-23 (trimmed to a few rows each) for the dossier lanes. Paths:
`nse_*.json` from `https://www.nseindia.in` + the path in each lane's spec (through `nse_api.Session`):
asm_long `/api/reportASM`, gsm `/api/reportGSM`, fii_dii `/api/fiidiiTradeReact` (today only: history builds up daily),
bulk_block `/api/snapshot-capital-market-largedeal`, results_calendar `/api/event-calendar?index=equities`,
announcements `/api/corporate-announcements?index=equities&from_date=DD-MM-YYYY&to_date=DD-MM-YYYY`,
financial_results `/api/corporates-financial-results?index=equities&period=Quarterly`.
`sec_bhavdata_full_DDMMYYYY.csv`: `https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_DDMMYYYY.csv` (delivery %).
`google_news_*.xml`: `https://news.google.com/rss/search?q=<quoted name>+NSE&hl=en-IN&gl=IN&ceid=IN:en`.
Not working: `/api/corporate-pledgedata?index=equities` returns empty lists; `/api/quote-equity` answers 403.
India VIX and sector indices are already in `index_levels` (from the daily index file).

`xbrl/`: quarterly results samples for lane R9 (see its spec in `docs/build-lanes.md`): the old per-company feed to Dec 2024 and the SEBI Integrated Filing feed from 2025.
