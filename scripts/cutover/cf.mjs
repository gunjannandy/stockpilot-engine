// The few Cloudflare API calls the cutover needs. `fetch` is injected for tests. The token is never logged.
const API = "https://api.cloudflare.com/client/v4";

export function createCf({ token, project, account, fetch: f = fetch }) {
  const call = async (method, path) => {
    const res = await f(`${API}${path}`, { method, headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" } });
    const body = await res.json().catch(() => ({}));
    if (!res.ok || body.success === false) throw new Error(`Cloudflare ${method} ${path.replace(/[0-9a-f]{32}/g, "<id>")} answered ${res.status}: ${(body.errors || []).map((e) => e.message).join("; ").slice(0, 160)}`);
    return body.result;
  };
  let acct = account;
  const base = async () => {
    if (!acct) {
      const list = await call("GET", "/accounts");
      if (list.length !== 1) throw new Error(`the token sees ${list.length} accounts; set CLOUDFLARE_ACCOUNT_ID`);
      acct = list[0].id;
    }
    return `/accounts/${acct}/pages/projects/${project}`;
  };
  return {
    // Names only: values of plain-text vars are dropped here so nothing can print them.
    async projectConfig() {
      const p = await call("GET", await base());
      const pick = (c) => ({ env_vars: Object.keys(c?.env_vars || {}), d1: Object.keys(c?.d1_databases || {}), kv: Object.keys(c?.kv_namespaces || {}) });
      return { production: pick(p.deployment_configs?.production), preview: pick(p.deployment_configs?.preview), productionBranch: p.production_branch };
    },
    async currentProduction() {
      const p = await call("GET", await base());
      return p.canonical_deployment?.id ?? null;
    },
    // Production only: Pages rolls back by making an earlier successful production deployment the live one.
    async rollback(id) { await call("POST", `${await base()}/deployments/${id}/rollback`); },
  };
}
