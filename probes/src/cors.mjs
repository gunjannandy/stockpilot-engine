// Would a browser on `origin` be allowed to read this response? (Actual cross-origin fetch rules, simple GET.)
export function corsVerdict(headers, origin) {
  const h = Object.fromEntries(Object.entries(headers).map(([k, v]) => [k.toLowerCase(), v]));
  const allow = h["access-control-allow-origin"];
  if (!allow) return { ok: false, reason: "no Access-Control-Allow-Origin header" };
  if (allow === "*" || allow === origin) return { ok: true, reason: allow };
  return { ok: false, reason: `Access-Control-Allow-Origin is ${allow}, not ${origin}` };
}
