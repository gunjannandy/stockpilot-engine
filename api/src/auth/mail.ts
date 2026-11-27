// The link email goes through the Apps Script's send endpoint (op=signin). True only on {ok: true}.
// The address and token are never logged.
import type { AuthEnv } from "./lib";

const TIMEOUT_MS = 25_000;

export async function sendLink(env: AuthEnv, to: string, token: string): Promise<boolean> {
  if (!env.GOOGLE_BRIDGE_URL || !env.GOOGLE_BRIDGE_KEY) return false;
  try {
    const url = new URL(env.GOOGLE_BRIDGE_URL);
    url.search = new URLSearchParams({
      key: env.GOOGLE_BRIDGE_KEY,
      op: "signin",
      to,
      t: token,
    }).toString();
    const res = await fetch(url.toString(), {
      redirect: "follow",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    if (!res.ok) return false;
    return ((await res.json()) as { ok?: boolean })?.ok === true;
  } catch {
    return false;
  }
}
