// The tracker's cron duty: when a secret is inside its 30-day window and not yet emailed, send the
// email to every person through the Apps Script's send endpoint, then mark it emailed. A failed send
// leaves it due, so the next run tries again. Names and addresses are never logged.
import { istText } from "../app";
import { type AuthEnv, people } from "../auth/lib";
import type { Core } from "../jobs/runtime";
import { secretsEmailSubject } from "./email";
import { tracker } from "./routes";

const PATH = "/api/email/secrets";

async function send(env: Record<string, string | undefined>, to: string, f: typeof fetch) {
  if (!env.GOOGLE_BRIDGE_URL || !env.GOOGLE_BRIDGE_KEY) return false;
  try {
    const url = new URL(env.GOOGLE_BRIDGE_URL);
    url.search = new URLSearchParams({
      key: env.GOOGLE_BRIDGE_KEY,
      op: "send",
      to,
      subject: secretsEmailSubject,
      path: PATH,
    }).toString();
    const res = await f(url.toString(), {
      redirect: "follow",
      signal: AbortSignal.timeout(25_000),
    });
    return res.ok && ((await res.json()) as { ok?: boolean })?.ok === true;
  } catch {
    return false;
  }
}

export async function runSecretsDuty(core: Core, f: typeof fetch = fetch): Promise<string> {
  const due = (await tracker(core)).secrets.filter((s) => s.due);
  if (!due.length) return "nothing due";
  const env = core.env as Record<string, string | undefined>;
  const to = Object.values(people(core.env as AuthEnv));
  if (!to.length) return "not sent: no people set";
  const results = await Promise.all(to.map((a) => send(env, a, f)));
  if (!results.every(Boolean))
    return `not sent: ${results.filter((r) => !r).length} failed, will retry`;
  const at = istText(core.now());
  for (const s of due)
    await core.d1
      .prepare("update secret_expiry set notified_at = ? where name = ?")
      .bind(at, s.name)
      .run();
  return `emailed ${due.length}`;
}
