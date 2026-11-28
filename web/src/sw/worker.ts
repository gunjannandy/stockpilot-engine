// Service worker source. The build turns this into /sw.js (see ../../sw-plugin.ts); do not add a copy to public/.
// Service worker: the page opens offline and shows the last data. Answers are kept per version.
const VERSION = "sp-v1";
const SHELL = "/";

type WorkerEvent = {
  request: Request;
  waitUntil: (p: Promise<unknown>) => void;
  respondWith: (p: Promise<Response>) => void;
};

const sw = self as unknown as {
  location: { origin: string };
  addEventListener: (type: string, fn: (e: WorkerEvent) => void) => void;
  skipWaiting: () => Promise<void>;
  clients: { claim: () => Promise<void> };
};

sw.addEventListener("install", (e) => {
  e.waitUntil(
    caches
      .open(VERSION)
      .then((c) => c.add(SHELL))
      .then(() => sw.skipWaiting()),
  );
});
sw.addEventListener("activate", (e) => {
  e.waitUntil(
    caches
      .keys()
      .then((ks) =>
        Promise.all(
          ks.filter((k) => k.startsWith("sp-") && k !== VERSION).map((k) => caches.delete(k)),
        ),
      )
      .then(() => sw.clients.claim()),
  );
});

async function networkFirst(req: Request, fallbackKey?: string | Request) {
  const cache = await caches.open(VERSION);
  try {
    const res = await fetch(req);
    if (res.ok) cache.put(fallbackKey ?? req, res.clone());
    return res;
  } catch (err) {
    const hit = await cache.match(fallbackKey ?? req);
    if (hit) return hit;
    throw err;
  }
}

sw.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== sw.location.origin) return;
  if (req.mode === "navigate") return void e.respondWith(networkFirst(req, SHELL));
  if (url.pathname.startsWith("/api/") && !url.pathname.startsWith("/api/auth"))
    return void e.respondWith(networkFirst(req));
  // Built files carry a hash in their name, so a stored copy is always right.
  if (url.pathname.startsWith("/assets/"))
    return void e.respondWith(
      caches.open(VERSION).then(async (c) => (await c.match(req)) ?? networkFirst(req)),
    );
});
