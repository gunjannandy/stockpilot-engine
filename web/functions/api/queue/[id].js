import { json } from "../../../lib/http.js";
import { get, remove } from "../../../lib/queue.js";

// Undo: only while the VM has not taken the request.
export async function onRequestDelete({ params, env }) {
  const item = await get(env, params.id);
  if (!item) return json({ error: "No such request." }, 404);
  if (item.taken_at) return json({ error: "Too late: it has already been picked up." }, 409);
  await remove(env, item.id);
  return json({ ok: true });
}
