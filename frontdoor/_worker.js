// The front door: the `stockpilotgn` Pages project after the v3 switch (docs/cutover-v3.md).
// One small function that passes every request to the App unchanged, so the address people use never changes.
// Deployed by Direct Upload: `wrangler pages deploy frontdoor --project-name stockpilotgn` (no build step).
//
// What it does not do: look at cookies, sign anybody in, or keep anything. Set-Cookie has no Domain (`__Host-` cookies
// cannot), so the browser keeps the cookie for this address. Redirects are handed back as they are, never followed:
// the App's own are relative, and Kite's callback (`/kite/callback`) arrives here and is passed on like any path.
// Plain JavaScript on purpose: Pages runs this file as it is.

/** Where the App lives. `APP_ORIGIN` (a Pages variable) overrides it, for a preview of the front door. */
export const DEFAULT_APP_ORIGIN = "https://stockpilot-app.stockpilotgn.workers.dev";

// Hop-by-hop and platform headers that must not be copied to the App.
const DROP = ["host", "content-length", "connection", "cf-connecting-ip", "x-forwarded-host"];

export function appUrl(request, appOrigin = DEFAULT_APP_ORIGIN) {
  const from = new URL(request.url);
  const to = new URL(appOrigin);
  to.pathname = from.pathname;
  to.search = from.search;
  return to;
}

/** Makes the request the App sees, or the response to give when the front door cannot pass it on. */
export async function passOn(request, env = {}, fetcher = fetch) {
  const origin =
    typeof env.APP_ORIGIN === "string" && env.APP_ORIGIN ? env.APP_ORIGIN : DEFAULT_APP_ORIGIN;
  const url = appUrl(request, origin);
  const headers = new Headers(request.headers);
  for (const name of DROP) headers.delete(name);
  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  let res;
  try {
    res = await fetcher(
      new Request(url, {
        method: request.method,
        headers,
        body: hasBody ? request.body : undefined,
        duplex: "half",
        redirect: "manual",
      }),
    );
  } catch {
    return new Response("StockPilot is not answering. Try again in a minute.", {
      status: 502,
      headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" },
    });
  }
  // A Location that names the App's own address would move the browser off this one: bring it back to a path.
  const loc = res.headers.get("location");
  if (loc) {
    try {
      const target = new URL(loc, url);
      if (target.origin === url.origin) {
        res = new Response(res.body, res);
        res.headers.set("location", target.pathname + target.search + target.hash);
      }
    } catch {
      // leave an unreadable Location alone
    }
  }
  return res;
}

export default {
  fetch(request, env) {
    return passOn(request, env);
  },
};
