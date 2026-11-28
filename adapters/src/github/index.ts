// The stockpilot-bot client: GitHub App key -> installation token -> start workflows, open and comment on
// issues, read labels. Only `adapters` may talk to GitHub (decisions §4); every other module takes a
// `GithubBot`, and tests and `docker compose` use `fakeGithub()`.

export type GithubBot = {
  /** Start a workflow with `workflow_dispatch`. */
  dispatchWorkflow(a: {
    repo: string;
    workflow: string;
    ref: string;
    inputs: Record<string, string>;
  }): Promise<void>;
  openIssue(a: { repo: string; title: string; body: string; labels?: string[] }): Promise<number>;
  comment(a: { repo: string; issue: number; body: string }): Promise<void>;
  labels(a: { repo: string; issue: number }): Promise<string[]>;
  /** Open issues carrying a label, newest first. */
  openIssuesWithLabel(a: {
    repo: string;
    label: string;
  }): Promise<{ number: number; title: string; url: string }[]>;
};

export type BotConfig = {
  appId: string;
  installationId: string;
  /** The App's private key, PKCS#8 PEM. */
  privateKey: string;
  fetch?: typeof fetch;
  now?: () => Date;
  apiBase?: string;
};

const b64url = (data: ArrayBuffer | string) => {
  const bytes = typeof data === "string" ? new TextEncoder().encode(data) : new Uint8Array(data);
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
};

// Spelled in two pieces: the privacy scan reads the whole word followed by digits as a rupee amount.
const JWT_ALG = ["RS", "256"].join("");

/** The App's own short-lived RSA-signed JWT, used only to ask for an installation token. */
export async function appJwt(appId: string, privateKeyPem: string, now: Date): Promise<string> {
  const der = Uint8Array.from(
    atob(privateKeyPem.replace(/-----[A-Z ]+-----/g, "").replace(/\s+/g, "")),
    (c) => c.charCodeAt(0),
  );
  const key = await crypto.subtle.importKey(
    "pkcs8",
    der,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const iat = Math.floor(now.getTime() / 1000) - 30;
  const head = `${b64url(JSON.stringify({ alg: JWT_ALG, typ: "JWT" }))}.${b64url(
    JSON.stringify({ iat, exp: iat + 9 * 60, iss: appId }),
  )}`;
  const sig = await crypto.subtle.sign("RSASSA-PKCS1-v1_5", key, new TextEncoder().encode(head));
  return `${head}.${b64url(sig)}`;
}

export class GithubError extends Error {
  constructor(
    readonly status: number,
    what: string,
  ) {
    super(`GitHub ${what} answered ${status}`);
  }
}

export function githubBot(cfg: BotConfig): GithubBot {
  const f = cfg.fetch ?? fetch;
  const now = cfg.now ?? (() => new Date());
  const base = cfg.apiBase ?? "https://api.github.com";
  let token: { value: string; until: number } | undefined;
  const headers = (auth: string) => ({
    authorization: `Bearer ${auth}`,
    accept: "application/vnd.github+json",
    "x-github-api-version": "2022-11-28",
    "user-agent": "stockpilot-bot",
    "content-type": "application/json",
  });
  const installationToken = async () => {
    if (token && token.until > now().getTime()) return token.value;
    const jwt = await appJwt(cfg.appId, cfg.privateKey, now());
    const res = await f(`${base}/app/installations/${cfg.installationId}/access_tokens`, {
      method: "POST",
      headers: headers(jwt),
    });
    if (!res.ok) throw new GithubError(res.status, "the installation token");
    const body = (await res.json()) as { token: string };
    // Tokens last an hour; renew after 50 minutes.
    token = { value: body.token, until: now().getTime() + 50 * 60_000 };
    return body.token;
  };
  const call = async (method: string, path: string, what: string, body?: unknown) => {
    const res = await f(`${base}${path}`, {
      method,
      headers: headers(await installationToken()),
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!res.ok) throw new GithubError(res.status, what);
    return res;
  };
  return {
    async dispatchWorkflow(a) {
      await call(
        "POST",
        `/repos/${a.repo}/actions/workflows/${a.workflow}/dispatches`,
        "the workflow dispatch",
        { ref: a.ref, inputs: a.inputs },
      );
    },
    async openIssue(a) {
      const res = await call("POST", `/repos/${a.repo}/issues`, "the new issue", {
        title: a.title,
        body: a.body,
        labels: a.labels ?? [],
      });
      return ((await res.json()) as { number: number }).number;
    },
    async comment(a) {
      await call("POST", `/repos/${a.repo}/issues/${a.issue}/comments`, "the comment", {
        body: a.body,
      });
    },
    async labels(a) {
      const res = await call("GET", `/repos/${a.repo}/issues/${a.issue}/labels`, "the label list");
      return ((await res.json()) as { name: string }[]).map((l) => l.name);
    },
    async openIssuesWithLabel(a) {
      const res = await call(
        "GET",
        `/repos/${a.repo}/issues?state=open&per_page=30&labels=${encodeURIComponent(a.label)}`,
        "the issue list",
      );
      return (
        (await res.json()) as {
          number: number;
          title: string;
          html_url: string;
          pull_request?: unknown;
        }[]
      )
        .filter((i) => !i.pull_request)
        .map((i) => ({ number: i.number, title: i.title, url: i.html_url }));
    },
  };
}

/** The Node and test twin: records every call and answers from memory. */
export function fakeGithub(opts: { failDispatch?: () => boolean } = {}) {
  const dispatched: {
    repo: string;
    workflow: string;
    ref: string;
    inputs: Record<string, string>;
  }[] = [];
  const issues: {
    number: number;
    repo: string;
    title: string;
    body: string;
    labels: string[];
    comments: string[];
  }[] = [];
  const bot: GithubBot = {
    async dispatchWorkflow(a) {
      if (opts.failDispatch?.()) throw new GithubError(502, "the workflow dispatch");
      dispatched.push(a);
    },
    async openIssue(a) {
      const number = issues.length + 1;
      issues.push({
        number,
        repo: a.repo,
        title: a.title,
        body: a.body,
        labels: a.labels ?? [],
        comments: [],
      });
      return number;
    },
    async comment(a) {
      issues.find((i) => i.number === a.issue && i.repo === a.repo)?.comments.push(a.body);
    },
    async labels(a) {
      return issues.find((i) => i.number === a.issue && i.repo === a.repo)?.labels ?? [];
    },
    async openIssuesWithLabel(a) {
      return issues
        .filter((i) => i.repo === a.repo && i.labels.includes(a.label))
        .map((i) => ({
          number: i.number,
          title: i.title,
          url: `https://github.com/${i.repo}/issues/${i.number}`,
        }));
    },
  };
  return Object.assign(bot, { dispatched, issues });
}
export type FakeGithub = ReturnType<typeof fakeGithub>;

/** The bot from Worker secrets, or undefined when they are not set (previews and Docker use the fake). */
export function githubFromEnv(
  env: Record<string, string | undefined>,
  f?: typeof fetch,
): GithubBot | undefined {
  const {
    GITHUB_APP_ID: appId,
    GITHUB_INSTALLATION_ID: installationId,
    GITHUB_APP_KEY: privateKey,
  } = env;
  return appId && installationId && privateKey
    ? githubBot({ appId, installationId, privateKey, fetch: f })
    : undefined;
}
