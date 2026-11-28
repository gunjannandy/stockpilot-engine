---
status: accepted
---
# Keep Lightweight Charts for the stock chart

The stock chart felt clunky: buy and sell ticks were small and hard to read, and layers (average line, forecast band, our buys) were added through a menu. We looked at the alternatives and decided to keep Lightweight Charts 5 and fix how we use it, not swap the library.

## Considered options

- **Lightweight Charts 5 (kept).** About 45 KB, canvas, made for price series, with price lines, series markers, custom primitives (our forecast band already uses one), a shared time axis for panes below the price and touch pinch and pan that feel right. Free under Apache 2.0. Weak spot: no built-in legend or layer toggles, so we draw those ourselves.
- **uPlot.** Smaller and fast, but a general time-series plotter: no candles, markers or price lines, so we would rebuild all of that.
- **Apache ECharts.** Rich (candlesticks, zoom bars, mark points) but around ten times the size and its look and touch feel are generic. It would slow the first load on a phone for little gain.
- **Highcharts Stock, TradingView Advanced Charts.** Best out of the box, but licences cost money or need approval, and the second ships its own UI that cannot follow our look.
- **Plotly, D3 by hand.** Too heavy or too much to own for one chart.

## Decision and consequences

Keep Lightweight Charts. The clunky parts were ours, so the fixes are in our code: layers become toggle chips next to the ranges (one tap each, state kept), buy and sell ticks become larger series markers with a plain-words tooltip, and the raw numbers sit in a table lower on the page (the chart is for shape, the table is for exact values). If a later need is beyond this library (for example drawing tools), revisit this record.
