import { sign } from "../app";

/** The nightly reseed call: the scheduler asks the preview Worker to reseed its database. Skips when no preview address is set. */
export async function callReseed(
  env: Record<string, string | undefined>,
  fetcher: typeof fetch = fetch,
): Promise<string> {
  const base = env.PREVIEW_URL;
  const key = env.INGEST_HMAC_KEY;
  if (!base) return "no preview address set: not reseeded";
  if (!key) return "no ingest key set: not reseeded";
  const body = "{}";
  const res = await fetcher(`${base.replace(/\/$/, "")}/api/previewseed/reseed`, {
    method: "POST",
    headers: { "content-type": "application/json", "x-signature": await sign(key, body) },
    body,
  });
  if (!res.ok) throw new Error(`preview reseed answered ${res.status}`);
  return "preview reseeded";
}
