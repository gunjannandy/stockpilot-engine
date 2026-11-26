import { json } from "../../../../lib/http.js";
import { lastCall, listAll } from "../../../../lib/queue.js";

// For the VM: when the page last used the KV queue, and how many requests still wait. The queue is retired a week after the last call.
export async function onRequestGet({ env }) {
  const pending = (await listAll(env)).filter((i) => i.status === "pending" || i.status === "taken").length;
  return json({ last_call_at: await lastCall(env), pending });
}
