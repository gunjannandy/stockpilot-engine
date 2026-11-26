import { json, readJson } from "../../../lib/http.js";
import { KINDS, add, guard, listAll, noteCall } from "../../../lib/queue.js";
import { syncedAt } from "../../../lib/kite.js";

// The browser's view: its requests with status, so the page can show pending, done or failed.
export async function onRequestGet({ env }) {
  await noteCall(env);
  const items = (await listAll(env)).slice(-100).map(({ id, kind, payload, by, at, status, note }) => ({ id, kind, payload, by, at, status, note }));
  return json({ items, kite_synced_at: await syncedAt(env) });
}

export async function onRequestPost({ request, env, data }) {
  await noteCall(env);
  const body = await readJson(request);
  if (!body || !KINDS.includes(body.kind)) return json({ error: "Unknown request kind." }, 400);
  if (body.payload !== undefined && (typeof body.payload !== "object" || body.payload === null || Array.isArray(body.payload))) {
    return json({ error: "payload must be an object." }, 400);
  }
  if (!data?.person) return json({ error: "Not signed in." }, 401);
  const refused = await guard(env, body.kind, body.payload ?? {});
  if (refused) return json({ error: refused.error }, refused.status);
  const item = await add(env, body.kind, body.payload ?? {}, data.person);
  return json({ id: item.id });
}
