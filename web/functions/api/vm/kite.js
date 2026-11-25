import { readAll } from "../../../lib/kite.js";
import { json } from "../../../lib/http.js";

export async function onRequestGet({ env }) {
  let data;
  try {
    data = await readAll(env);
  } catch (err) {
    return json({ error: String(err.message || err) }, 502);
  }
  if (!data) return json({ login_needed: true }, 409);
  return json({ fetched_at: new Date().toISOString(), ...data });
}
