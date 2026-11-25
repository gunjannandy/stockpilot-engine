import { json } from "../../../../lib/http.js";
import { listAll, markTaken } from "../../../../lib/queue.js";

export async function onRequestGet({ request, env }) {
  const after = new URL(request.url).searchParams.get("after") || "";
  const out = [];
  for (const item of await listAll(env)) {
    if (item.id <= after || item.status === "done" || item.status === "failed") continue;
    const taken = await markTaken(env, item);
    out.push({ id: taken.id, kind: taken.kind, payload: taken.payload, by: taken.by, at: taken.at });
  }
  return json(out);
}
