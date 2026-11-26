// Probe 4: run from a Cloudflare Worker to see whether Yahoo and NSE answer Worker egress.
// Deploy as a throwaway with `wrangler deploy` from the VM, call /?s=TCS, then delete it. Synthetic: no private data.
import { parseYahooChart, parseNseQuote } from "./quotes.mjs";

export default {
  async fetch(req) {
    const s = new URL(req.url).searchParams.get("s") || "TCS";
    const out = {};
    const t0 = Date.now();
    const y = await fetch(`https://query1.finance.yahoo.com/v8/finance/chart/${s}.NS?range=1d&interval=1m`, { headers: { "user-agent": "Mozilla/5.0" } });
    out.yahoo = { status: y.status, ms: Date.now() - t0, quote: y.ok ? parseYahooChart(await y.json(), Math.floor(Date.now() / 1000)) : null };
    const t1 = Date.now();
    const home = await fetch("https://www.nseindia.com/", { headers: { "user-agent": "Mozilla/5.0", accept: "text/html" } });
    const cookie = (home.headers.getSetCookie?.() || []).map((c) => c.split(";")[0]).join("; ");
    const n = await fetch(`https://www.nseindia.com/api/quote-equity?symbol=${s}`, { headers: { "user-agent": "Mozilla/5.0", cookie, accept: "application/json", referer: "https://www.nseindia.com/" } });
    out.nse = { status: n.status, ms: Date.now() - t1, quote: n.ok ? parseNseQuote(await n.json()) : null };
    return Response.json(out);
  },
};
