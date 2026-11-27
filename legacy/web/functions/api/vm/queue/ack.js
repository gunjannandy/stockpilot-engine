import { json, readJson } from "../../../../lib/http.js";
import { finish, get } from "../../../../lib/queue.js";

export async function onRequestPost({ request, env }) {
  const body = await readJson(request);
  if (!body || !["done", "failed"].includes(body.status) || typeof body.id !== "string") {
    return json({ error: "Need id and status done or failed." }, 400);
  }
  const item = await get(env, body.id);
  if (!item) return json({ error: "No such request." }, 404);
  await finish(env, item, body.status, String(body.note ?? "").slice(0, 500));
  return json({ ok: true });
}
