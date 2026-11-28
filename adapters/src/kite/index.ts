// Kite Connect, read only. These are the only Kite paths this project may call (a test checks the
// source): no order endpoint is listed here and none is ever added. Only `adapters` may talk to Kite.

export const READ_PATHS = {
  holdings: "/portfolio/holdings",
  mf_holdings: "/mf/holdings",
  trades: "/trades",
  positions: "/portfolio/positions",
  margins: "/user/margins",
  gtts: "/gtt/triggers",
} as const;
export const SESSION_PATH = "/session/token";

export type KiteData = {
  holdings: Record<string, unknown>[];
  mf_holdings: Record<string, unknown>[];
  trades: Record<string, unknown>[];
  positions: unknown;
  margins: unknown;
  gtts: unknown;
};

export type KiteClient = {
  /** Where the browser goes to log in (an absolute Kite URL, or a local one for the mock). */
  loginUrl(): string;
  /** Trade the one-time request token for today's access token, or null when Kite refuses. */
  exchange(requestToken: string): Promise<string | null>;
  /** The six reads. */
  read(accessToken: string): Promise<KiteData>;
};

const sha256Hex = async (text: string) =>
  [...new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text)))]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

export function kiteClient(cfg: {
  apiKey: string;
  apiSecret: string;
  apiBase?: string;
  loginBase?: string;
  fetch?: typeof fetch;
}): KiteClient {
  const f = cfg.fetch ?? fetch;
  const api = (cfg.apiBase ?? "https://api.kite.trade").replace(/\/$/, "");
  const login = (cfg.loginBase ?? "https://kite.zerodha.com").replace(/\/$/, "");
  return {
    loginUrl: () => `${login}/connect/login?v=3&api_key=${encodeURIComponent(cfg.apiKey)}`,
    async exchange(requestToken) {
      const checksum = await sha256Hex(cfg.apiKey + requestToken + cfg.apiSecret);
      const res = await f(api + SESSION_PATH, {
        method: "POST",
        headers: { "X-Kite-Version": "3", "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({
          api_key: cfg.apiKey,
          request_token: requestToken,
          checksum,
        }),
      });
      const body = (await res.json().catch(() => null)) as {
        status?: string;
        data?: { access_token?: string };
      } | null;
      if (!res.ok || body?.status !== "success" || !body.data?.access_token) return null;
      return body.data.access_token;
    },
    async read(accessToken) {
      const headers = {
        "X-Kite-Version": "3",
        Authorization: `token ${cfg.apiKey}:${accessToken}`,
      };
      const out: Record<string, unknown> = {};
      for (const [name, path] of Object.entries(READ_PATHS)) {
        const res = await f(api + path, { headers });
        if (!res.ok) throw new Error(`Kite ${path} answered ${res.status}`);
        out[name] = ((await res.json()) as { data: unknown }).data;
      }
      return out as KiteData;
    },
  };
}

/** The mock for previews, tests and Docker: login comes straight back to the callback, the data is made up. */
export function fakeKite(
  data: Partial<KiteData> = {},
  opts: { refuse?: boolean } = {},
): KiteClient & { reads: number } {
  const state = { reads: 0 };
  return Object.assign(state, {
    loginUrl: () => "/kite/callback?request_token=mock&status=success",
    async exchange(token: string) {
      return opts.refuse || !token ? null : "mock-access";
    },
    async read() {
      state.reads++;
      return {
        holdings: [
          {
            tradingsymbol: "AAA",
            isin: "XX0000000001",
            quantity: 10,
            t1_quantity: 0,
            average_price: 100,
          },
          {
            tradingsymbol: "BBB",
            isin: "XX0000000002",
            quantity: 5,
            t1_quantity: 1,
            average_price: 250,
          },
        ],
        mf_holdings: [],
        trades: [
          {
            trade_id: "T1",
            order_id: "O1",
            tradingsymbol: "AAA",
            transaction_type: "BUY",
            quantity: 2,
            average_price: 101,
            fill_timestamp: "2026-11-26 10:15:00",
          },
        ],
        positions: { net: [], day: [] },
        margins: {},
        gtts: [],
        ...data,
      } satisfies KiteData;
    },
  });
}

/** The client from Worker secrets. Without keys only previews and local runs get the mock; production gets none, never made-up holdings. */
export function kiteFromEnv(
  env: Record<string, string | undefined>,
  f?: typeof fetch,
): KiteClient | undefined {
  const { KITE_API_KEY: apiKey, KITE_API_SECRET: apiSecret } = env;
  if (apiKey && apiSecret)
    return kiteClient({
      apiKey,
      apiSecret,
      apiBase: env.KITE_API_BASE,
      loginBase: env.KITE_LOGIN_BASE,
      fetch: f,
    });
  return env.SP_ENV === "preview" || env.SP_ENV === "dev" ? fakeKite() : undefined;
}
