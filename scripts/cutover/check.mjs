// The hard-block check (ticket V4) against one URL, behind the real sign-in gate when there is one.
// The gate is a signed session cookie, so the check mints a real one for the owner from SP_COOKIE_KEY (from the VM .env).
// The cookie value is never printed.
import { createRequire } from "node:module";
import { signSession } from "../../web/lib/auth.js";
import { compareToday, verdict } from "./lib.mjs";

export async function mintCookie(env, person = "owner") {
  return { name: "sp_session", value: await signSession(person, env?.SP_COOKIE_KEY) };
}

const SETTLE_MS = 6000;

const defaultLaunch = async () => createRequire(import.meta.url)("playwright").chromium.launch({ args: ["--no-sandbox"] });

// Proves the browser check can run: loads playwright and launches then closes chromium. Run BEFORE anything is uploaded.
export async function probeBrowser({ launch = defaultLaunch } = {}) {
  try {
    const b = await launch();
    await b.close();
    return { ok: true, text: "Browser check can run." };
  } catch (e) {
    return { ok: false, text: `The browser check cannot run (${String(e?.message || e).slice(0, 160)}), so no deploy. On the VM run at the repo root: npm i --no-save playwright@1.65.1 (ops/install.sh does it), then try again.` };
  }
}

// launch: () => Promise<browser>; defaults to Playwright's Chromium (pre-installed on the VM and in cloud sessions).
export async function checkUrl(url, { cookie, launch, timeoutMs = 30000 } = {}) {
  launch ||= defaultLaunch;
  const browser = await launch();
  const out = { url, loaded: false, gate: false, pageErrors: [], rows: 0, expectedRows: 0, nothingLine: false, mismatches: [], notes: [] };
  try {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    if (cookie) await context.addCookies([{ name: cookie.name, value: cookie.value, url, httpOnly: true, secure: url.startsWith("https") }]);
    const page = await context.newPage();
    page.on("pageerror", (e) => out.pageErrors.push(String(e?.message || e).slice(0, 200)));
    const res = await page.goto(url, { waitUntil: "domcontentloaded", timeout: timeoutMs }).catch((e) => { out.notes.push(`goto: ${String(e.message).slice(0, 120)}`); return null; });
    out.loaded = !!res && res.status() === 200;
    if (new URL(page.url()).pathname.startsWith("/login")) { out.gate = true; out.notes.push("the sign-in page answered: the session cookie was not accepted (SP_COOKIE_KEY differs from the project's, or SP_PEOPLE has no owner)"); }
    if (out.loaded && !out.gate) {
      await page.waitForSelector(".lrow, main", { timeout: timeoutMs }).catch(() => {});
      await page.waitForTimeout(SETTLE_MS);
      const todayRes = await context.request.get(new URL("data/today.json", url).href);
      const today = todayRes.ok() ? await todayRes.json() : null;
      if (!today) { out.mismatches.push(`data/today.json answered ${todayRes.status()}`); }
      const rows = await page.$$eval('.lrow[data-sel^="today:"]', (els) => els.map((e) => ({ sym: e.getAttribute("data-sel").slice(6), text: e.innerText.replace(/\s+/g, " ") })));
      out.rows = rows.length;
      out.expectedRows = today ? (today.buy?.length || 0) + (today.sell?.length || 0) : -1;
      out.nothingLine = /nothing to do today/i.test(await page.evaluate(() => document.body.innerText));
      if (today) out.mismatches.push(...compareToday(rows, today).mismatches);
    }
  } finally {
    await browser.close().catch(() => {});
  }
  return { ...verdict(out), detail: out };
}
