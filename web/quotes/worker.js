// Quote Worker (ticket T15): every 5 minutes in market hours, refresh prices for the stocks in the news.
// No web endpoint: only the timer calls it. Needs the D1 binding DB and no secrets (public data only).
// Free Worker limits: 12 stocks x (Yahoo + NSE) + 1 cookie call + 3 D1 calls stays under 50 subrequests and uses
// almost no CPU (the waits between calls are not CPU); at most 12 x 75 runs = 900 rows written a day.
import { marketOpen, newsSymbols, refreshQuotes } from "../lib/v2/quotes.js";

export default {
  async scheduled(_event, env, ctx = {}) {
    const now = ctx.now ?? new Date();
    if (!marketOpen(now)) return { written: 0, failed: [], stopped: false };
    const symbols = await newsSymbols(env.DB, now);
    if (!symbols.length) return { written: 0, failed: [], stopped: false };
    return refreshQuotes({ db: env.DB, symbols, fetch: ctx.fetch ?? fetch, now, sleep: ctx.sleep });
  },
};
