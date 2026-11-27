// ETag-aware pane fetch. A 304 gives back the answer the browser already holds; a contract version
// that differs from this bundle's, or the server's own "updating" answer, raises PaneUpdating so
// the page shows the calm updating state instead of a broken pane.
import { CONTRACT_HEADER, CONTRACT_VERSION } from "@stockpilot/contract";

export class PaneUpdating extends Error {
  constructor() {
    super("updating");
  }
}
export class PaneHttpError extends Error {
  constructor(
    readonly status: number,
    path: string,
  ) {
    super(`GET ${path} failed: ${status}`);
  }
}

export type Held<T> = { etag: string | null; data: T };
export type PaneFetcher = (url: string, init?: RequestInit) => Promise<Response>;

/** `held` is what the cache has now for this path (its ETag and body), or undefined. */
export async function fetchPane<T>(
  path: string,
  held?: Held<T>,
  fetcher: PaneFetcher = (u, i) => fetch(u, i),
  version: string = CONTRACT_VERSION,
): Promise<Held<T>> {
  const headers: Record<string, string> = {};
  if (held?.etag) headers["if-none-match"] = held.etag;
  const res = await fetcher(path, { headers });
  const theirs = res.headers.get(CONTRACT_HEADER);
  if (theirs && theirs !== version) throw new PaneUpdating();
  if (res.status === 304 && held) return held;
  if (res.status === 503) {
    const body = (await res.json().catch(() => ({}))) as { error?: string };
    if (body.error === "updating") throw new PaneUpdating();
  }
  if (!res.ok) throw new PaneHttpError(res.status, path);
  return { etag: res.headers.get("etag"), data: (await res.json()) as T };
}
