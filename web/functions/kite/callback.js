import { exchangeToken, storeToken } from "../../lib/kite.js";
import { json } from "../../lib/http.js";
import { add } from "../../lib/queue.js";

export async function onRequestGet({ request, env }) {
  const url = new URL(request.url);
  const requestToken = url.searchParams.get("request_token");
  if (!requestToken || url.searchParams.get("status") === "error") {
    return json({ error: "Kite login did not complete." }, 400);
  }
  const accessToken = await exchangeToken(env, requestToken);
  if (!accessToken) return json({ error: "Kite refused the login. Press Sync now to try again." }, 502);
  await storeToken(env, accessToken);
  await add(env, "rerun", { job: "kite" }, "kite-login");   // pull holdings at the next queue tick, not at 7 pm
  return Response.redirect(new URL("/?synced=1", url).toString(), 302);
}
