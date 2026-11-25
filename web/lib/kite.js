// Kite Connect, read only. These are the only Kite paths this project may call (a test checks the source).
export const READ_PATHS = {
  holdings: "/portfolio/holdings",
  mf_holdings: "/mf/holdings",
  trades: "/trades",
  positions: "/portfolio/positions",
  margins: "/user/margins",
  gtts: "/gtt/triggers",
};
export const SESSION_PATH = "/session/token";

const TOKEN_KEY = "kite:token";
const SYNCED_KEY = "kite:synced_at";

export const apiBase = (env) => (env.KITE_API_BASE || "https://api.kite.trade").replace(/\/$/, "");
export const loginBase = (env) => (env.KITE_LOGIN_BASE || "https://kite.zerodha.com").replace(/\/$/, "");

// Seconds until the next 06:00 IST (00:30 UTC): Kite tokens die then.
export function secondsUntilSix(now = new Date()) {
  const next = new Date(now);
  next.setUTCHours(0, 30, 0, 0);
  if (next <= now) next.setUTCDate(next.getUTCDate() + 1);
  return Math.max(60, Math.floor((next - now) / 1000));
}

async function sha256Hex(text) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function exchangeToken(env, requestToken) {
  const checksum = await sha256Hex(env.KITE_API_KEY + requestToken + env.KITE_API_SECRET);
  const res = await fetch(apiBase(env) + SESSION_PATH, {
    method: "POST",
    headers: { "X-Kite-Version": "3", "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ api_key: env.KITE_API_KEY, request_token: requestToken, checksum }),
  });
  const body = await res.json().catch(() => null);
  if (!res.ok || body?.status !== "success" || !body?.data?.access_token) return null;
  return body.data.access_token;
}

export async function storeToken(env, accessToken, now = new Date()) {
  await env.SP.put(TOKEN_KEY, accessToken, { expirationTtl: secondsUntilSix(now) });
  await env.SP.put(SYNCED_KEY, now.toISOString());
}

export const syncedAt = (env) => env.SP.get(SYNCED_KEY);

// All six reads, or null when there is no usable token today.
export async function readAll(env) {
  const token = await env.SP.get(TOKEN_KEY);
  if (!token) return null;
  const headers = { "X-Kite-Version": "3", Authorization: `token ${env.KITE_API_KEY}:${token}` };
  const out = {};
  for (const [name, path] of Object.entries(READ_PATHS)) {
    const res = await fetch(apiBase(env) + path, { headers });
    if (res.status === 403) {
      await env.SP.delete(TOKEN_KEY); // expired or revoked
      return null;
    }
    if (!res.ok) throw new Error(`Kite ${path} answered ${res.status}`);
    out[name] = (await res.json()).data;
  }
  return out;
}
