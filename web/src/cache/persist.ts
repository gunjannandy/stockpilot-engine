// A persisted query cache: the page draws from the last data at once and refreshes quietly.
// Stored under the contract version, so a new contract never reads an old shape.
import { CONTRACT_VERSION } from "@stockpilot/contract";
import { dehydrate, hydrate, QueryClient } from "@tanstack/react-query";

export const CACHE_KEY = `sp-cache-${CONTRACT_VERSION}`;
const MAX_AGE_MS = 7 * 24 * 3600 * 1000;

type Store = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export function makeClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { gcTime: MAX_AGE_MS, staleTime: 15_000, refetchOnWindowFocus: true },
    },
  });
}

/** Fills the client from storage now (so the first render has data), then saves on every change. */
export function persistClient(
  client: QueryClient,
  store: Store = localStorage,
  now: () => number = Date.now,
): () => void {
  try {
    const raw = store.getItem(CACHE_KEY);
    if (raw) {
      const saved = JSON.parse(raw) as { at: number; state: Parameters<typeof hydrate>[1] };
      if (now() - saved.at < MAX_AGE_MS) hydrate(client, saved.state);
      else store.removeItem(CACHE_KEY);
    }
  } catch {
    store.removeItem(CACHE_KEY);
  }
  let timer: ReturnType<typeof setTimeout> | undefined;
  const save = () => {
    timer = undefined;
    try {
      const state = dehydrate(client, {
        shouldDehydrateQuery: (q) => q.state.status === "success" && q.queryKey[0] === "pane",
      });
      store.setItem(CACHE_KEY, JSON.stringify({ at: now(), state }));
    } catch {
      // Storage full or blocked: the page works, it just opens slower next time.
    }
  };
  const off = client.getQueryCache().subscribe(() => {
    timer ??= setTimeout(save, 500);
  });
  return () => {
    off();
    if (timer) clearTimeout(timer);
  };
}

/** Sign-out: nothing of the person's data stays in the browser. */
export function clearPersisted(client: QueryClient, store: Store = localStorage) {
  store.removeItem(CACHE_KEY);
  client.clear();
}
