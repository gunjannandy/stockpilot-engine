// The sign-in pages: self-contained HTML (no scripts, fonts or other files), because they are the only
// pages open without a session. English first, Kolkata Bengali beneath, trade words stay in English letters.

const esc = (s: string) =>
  s.replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] as string,
  );

const page = (inner: string) => `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>stockpilot · Sign in</title>
<style>
  :root { --bg:#f6f5f1; --card:#fff; --ink:#1d1f21; --muted:#5b6066; --line:#d9d7cf; --accent:#1f5f8b; --accent-ink:#fff; --warn:#a33a1f; }
  @media (prefers-color-scheme: dark) { :root { --bg:#16181a; --card:#1f2225; --ink:#ecebe6; --muted:#a3a7ab; --line:#363a3e; --accent:#6fb1de; --accent-ink:#0d1114; --warn:#f08a6c; } }
  * { box-sizing: border-box; }
  body { margin:0; min-height:100vh; display:grid; place-items:center; background:var(--bg); color:var(--ink); font:18px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; padding:16px; }
  main { width:100%; max-width:420px; background:var(--card); border:1px solid var(--line); border-radius:12px; padding:32px; }
  h1 { font-size:26px; margin:0 0 4px; }
  p { margin:0 0 16px; color:var(--muted); }
  .bn { font-size:16px; }
  label { display:block; font-weight:600; margin-bottom:8px; }
  input[type=email] { width:100%; font:inherit; font-size:20px; padding:14px 12px; border:1px solid var(--line); border-radius:10px; background:var(--bg); color:var(--ink); }
  input[type=email]:focus-visible { outline:3px solid var(--accent); outline-offset:2px; }
  button { margin-top:16px; width:100%; font:inherit; font-size:24px; font-weight:600; padding:20px 12px; border:0; border-radius:10px; background:var(--accent); color:var(--accent-ink); cursor:pointer; }
  a { color:var(--accent); font-weight:600; }
  .msg { color:var(--warn); font-weight:600; }
  .ok { color:var(--ink); font-weight:600; }
</style>
</head>
<body>
<main>
  <h1>stockpilot</h1>
${inner}
</main>
</body>
</html>`;

export function loginPage({ next = "/", message = "" } = {}) {
  return page(`  <p>Type your email address. We will send you a link to press.</p>
  <p class="bn" lang="bn">আপনার ইমেল ঠিকানা লিখুন। আমরা একটি লিংক পাঠাব, সেটি চাপুন।</p>
  ${message ? `<p class="msg" role="alert">${esc(message)}</p>` : ""}
  <form method="post" action="/login">
    <input type="hidden" name="next" value="${esc(next)}">
    <label for="email">Email address</label>
    <input id="email" type="email" name="email" autocomplete="email" autocapitalize="off" spellcheck="false" maxlength="254" required autofocus>
    <button type="submit">Send sign-in link</button>
  </form>`);
}

/** The same words for every address: the page never says who can sign in. */
export const sentPage = () =>
  page(`  <p class="ok">If that address can sign in, we have emailed a link. Open it on this computer; it works once, for 15 minutes.</p>
  <p class="bn" lang="bn">ঠিকানাটি ঠিক হলে আমরা একটি লিংক পাঠিয়েছি। এই কম্পিউটারে খুলুন; এটি ১৫ মিনিট, একবারই চলবে।</p>
  <p><a href="/login">Back</a></p>`);

export const confirmPage = (token: string) =>
  page(`  <p>Press the button to sign in. This computer will remember you for a year.</p>
  <p class="bn" lang="bn">সাইন ইন করতে বোতাম চাপুন। এই কম্পিউটার আপনাকে এক বছর মনে রাখবে।</p>
  <form method="post" action="/login/verify">
    <input type="hidden" name="t" value="${esc(token)}">
    <button type="submit">Sign in</button>
  </form>`);

export const expiredPage = () =>
  page(`  <p class="msg" role="alert">This link has expired or was used. Ask for a new one.</p>
  <p><a href="/login">Get a new link</a></p>`);
