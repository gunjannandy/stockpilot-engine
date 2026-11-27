// A written fallback and a check for each outside dependency (decisions §6). A check never throws:
// one source failing is a row, not an outage.
import { istText } from "../app";
import type { Core } from "../jobs/runtime";

export type Dependency = {
  id: string;
  /** What we do when it is down, in one line. */
  fallback: string;
  /** Public address to probe; none means the check reads our own records. */
  url?: string;
  check?(c: Core): Promise<{ ok: boolean; detail: string }>;
};

export const DEPENDENCIES: Dependency[] = [
  {
    id: "nse",
    url: "https://www.nseindia.com",
    fallback:
      "Show the last good data with its date; the calendar Job retries from the public runner.",
  },
  {
    id: "bse",
    url: "https://www.bseindia.com",
    fallback: "Use NSE alone; corporate actions wait for the next good run.",
  },
  {
    id: "yahoo",
    url: "https://query1.finance.yahoo.com/v7/finance/quote?symbols=AAPL",
    fallback: "Keep yesterday's prices and mark them stale.",
  },
  {
    id: "amfi",
    url: "https://www.amfiindia.com",
    fallback: "Keep the last fund NAVs with their date.",
  },
  {
    id: "google_news",
    url: "https://news.google.com/rss",
    fallback: "Show no news line rather than an old one.",
  },
  {
    id: "kite",
    url: "https://kite.zerodha.com",
    fallback: "Holdings stay at the last Sync; read-only, no orders either way.",
  },
  {
    id: "claude_usage",
    fallback: "Models are skipped past their daily cap; code-only calls still run.",
    async check(c) {
      const r = (await c.d1
        .prepare("select coalesce(sum(used), 0) as n from model_usage")
        .first()) as { n: number } | null;
      return { ok: true, detail: `${r?.n ?? 0} model calls recorded` };
    },
  },
  {
    id: "github_actions",
    url: "https://www.githubstatus.com/api/v2/status.json",
    fallback: "Jobs wait; the scheduler dispatches again within 3 minutes of recovery.",
  },
  {
    id: "cloudflare_limits",
    url: "https://www.cloudflarestatus.com/api/v2/status.json",
    fallback: "Writes stay inside the daily budget; archive old rows before a cap.",
  },
];

export async function checkDeps(c: Core, opts: { fetch?: typeof fetch; deps?: Dependency[] } = {}) {
  const f = opts.fetch ?? fetch;
  const at = istText(c.now());
  const out: { dep: string; ok: boolean; detail: string }[] = [];
  for (const d of opts.deps ?? DEPENDENCIES) {
    let r: { ok: boolean; detail: string };
    try {
      if (d.check) r = await d.check(c);
      else {
        const res = await f(d.url as string, { method: "GET", signal: AbortSignal.timeout(5000) });
        r = { ok: res.status < 500, detail: `answered ${res.status}` };
      }
    } catch (e) {
      r = { ok: false, detail: `unreachable: ${e instanceof Error ? e.message : e}`.slice(0, 200) };
    }
    await c.d1
      .prepare(
        `insert into dep_checks (dep, ok, detail, fallback, at) values (?, ?, ?, ?, ?)
         on conflict(dep) do update set ok = excluded.ok, detail = excluded.detail, fallback = excluded.fallback, at = excluded.at`,
      )
      .bind(d.id, r.ok ? 1 : 0, r.detail, d.fallback, at)
      .run();
    out.push({ dep: d.id, ...r });
  }
  return out;
}
