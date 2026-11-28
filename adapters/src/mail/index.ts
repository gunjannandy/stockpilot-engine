// The sign-in link mailer: the Apps Script's send endpoint (op=signin). Only `adapters` talks to it;
// `api` takes a `Mailer`, and Node and tests can use `fakeMailer()`. The address and token are never logged.

export type Mailer = {
  /** True only when the send endpoint answers {ok: true}. Never throws. */
  sendSigninLink(to: string, token: string, base?: string): Promise<boolean>;
};

const TIMEOUT_MS = 25_000;

export function bridgeMailer(cfg: { url: string; key: string; fetch?: typeof fetch }): Mailer {
  return {
    async sendSigninLink(to, token, base) {
      try {
        const url = new URL(cfg.url);
        url.search = new URLSearchParams({
          key: cfg.key,
          op: "signin",
          to,
          t: token,
          ...(base ? { base } : {}),
        }).toString();
        const res = await (cfg.fetch ?? fetch)(url.toString(), {
          redirect: "follow",
          signal: AbortSignal.timeout(TIMEOUT_MS),
        });
        if (!res.ok) return false;
        return ((await res.json()) as { ok?: boolean })?.ok === true;
      } catch {
        return false;
      }
    },
  };
}

/** The Node and test twin: records what would have been sent, can be told to fail. */
export function fakeMailer(opts: { fail?: boolean } = {}) {
  const sent: { to: string; token: string }[] = [];
  const mailer: Mailer = {
    async sendSigninLink(to, token) {
      if (opts.fail) return false;
      sent.push({ to, token });
      return true;
    },
  };
  return Object.assign(mailer, { sent });
}
export type FakeMailer = ReturnType<typeof fakeMailer>;

export function mailerFromEnv(
  env: { GOOGLE_BRIDGE_URL?: string; GOOGLE_BRIDGE_KEY?: string },
  f?: typeof fetch,
): Mailer | undefined {
  return env.GOOGLE_BRIDGE_URL && env.GOOGLE_BRIDGE_KEY
    ? bridgeMailer({ url: env.GOOGLE_BRIDGE_URL, key: env.GOOGLE_BRIDGE_KEY, fetch: f })
    : undefined;
}
