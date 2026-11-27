// Installs the app: registers the service worker (served from /sw.js) so the last data shows offline.
export function registerApp(nav: Navigator = navigator): void {
  if (!("serviceWorker" in nav)) return;
  const go = () => void nav.serviceWorker.register("/sw.js").catch(() => {});
  if (document.readyState === "complete") go();
  else window.addEventListener("load", go, { once: true });
}

/** Sign-out: the worker's stored answers go too. */
export async function clearOffline(): Promise<void> {
  if (typeof caches === "undefined") return;
  for (const k of await caches.keys()) if (k.startsWith("sp-")) await caches.delete(k);
}
