// The Cloudflare deployments client. Its token can only list and create deployments of the one Worker
// (a deployments-only token, held as a Worker secret), so a rollback is all it can do. Only `adapters`
// talks to Cloudflare (decisions §4); everything else takes a `Platform`.

export type Platform = {
  /** Put the previous deployment's version back at 100%. Returns the version restored. */
  rollback(): Promise<{ restored: string }>;
};

export class CloudflareError extends Error {
  constructor(
    readonly status: number,
    what: string,
  ) {
    super(`Cloudflare ${what} answered ${status}`);
  }
}

type Deployment = { id: string; versions: { version_id: string; percentage: number }[] };

export function cloudflarePlatform(cfg: {
  accountId: string;
  worker: string;
  token: string;
  fetch?: typeof fetch;
  apiBase?: string;
}): Platform {
  const f = cfg.fetch ?? fetch;
  const url = `${cfg.apiBase ?? "https://api.cloudflare.com/client/v4"}/accounts/${cfg.accountId}/workers/scripts/${cfg.worker}/deployments`;
  const headers = { authorization: `Bearer ${cfg.token}`, "content-type": "application/json" };
  return {
    async rollback() {
      const list = await f(url, { headers });
      if (!list.ok) throw new CloudflareError(list.status, "the deployment list");
      const body = (await list.json()) as { result?: { deployments?: Deployment[] } };
      // Newest first. The live one is [0]; go back to the nearest one on a different version.
      const all = body.result?.deployments ?? [];
      const live = all[0]?.versions[0]?.version_id;
      const prev = all.slice(1).find((d) => d.versions[0] && d.versions[0].version_id !== live);
      const target = prev?.versions[0]?.version_id;
      if (!target) throw new Error("no earlier deployment to roll back to");
      const res = await f(url, {
        method: "POST",
        headers,
        body: JSON.stringify({
          strategy: "percentage",
          versions: [{ version_id: target, percentage: 100 }],
        }),
      });
      if (!res.ok) throw new CloudflareError(res.status, "the rollback");
      return { restored: target };
    },
  };
}

/** The Node and test twin: records rollbacks, can be told to fail. */
export function fakePlatform(opts: { fail?: boolean } = {}) {
  const rollbacks: string[] = [];
  const platform: Platform = {
    async rollback() {
      if (opts.fail) throw new CloudflareError(500, "the rollback");
      rollbacks.push("previous");
      return { restored: "previous" };
    },
  };
  return Object.assign(platform, { rollbacks });
}
export type FakePlatform = ReturnType<typeof fakePlatform>;

export function platformFromEnv(
  env: Record<string, string | undefined>,
  f?: typeof fetch,
): Platform | undefined {
  const { CF_DEPLOY_TOKEN: token, CF_ACCOUNT_ID: accountId, CF_WORKER_NAME: worker } = env;
  return token && accountId
    ? cloudflarePlatform({ token, accountId, worker: worker ?? "stockpilot-app", fetch: f })
    : undefined;
}
