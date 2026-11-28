// @vitest-environment node
// C-015: the manifest installs (name, start url, icons that exist) and the worker answers offline
// from what it kept.
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import vm from "node:vm";
import { describe, expect, it } from "vitest";
import { compileWorker } from "../../sw-plugin";

const pub = join(__dirname, "../../public");

describe("manifest", () => {
  const m = JSON.parse(readFileSync(join(pub, "manifest.webmanifest"), "utf8"));
  it("is installable: name, start url, standalone, 192 and 512 icons that exist", () => {
    expect(m.name).toBeTruthy();
    expect(m.start_url).toBe("/");
    expect(m.display).toBe("standalone");
    const sizes = m.icons.map((i: { sizes: string }) => i.sizes);
    expect(sizes).toContain("192x192");
    expect(sizes).toContain("512x512");
    for (const i of m.icons) expect(existsSync(join(pub, i.src.slice(1)))).toBe(true);
  });
  it("is linked from the page", () => {
    expect(readFileSync(join(__dirname, "../../index.html"), "utf8")).toContain(
      "manifest.webmanifest",
    );
  });
});

async function loadWorker() {
  const store = new Map<string, Response>();
  const listeners: Record<string, (e: unknown) => void> = {};
  let online = true;
  const cache = {
    match: async (k: unknown) => store.get(typeof k === "string" ? k : (k as Request).url)?.clone(),
    put: async (k: unknown, r: Response) =>
      void store.set(typeof k === "string" ? k : (k as Request).url, r),
    add: async () => {},
  };
  const self = {
    location: { origin: "https://x.test" },
    addEventListener: (n: string, f: (e: unknown) => void) => {
      listeners[n] = f;
    },
    skipWaiting: async () => {},
    clients: { claim: async () => {} },
  };
  const ctx = {
    self,
    caches: { open: async () => cache, keys: async () => [], delete: async () => true },
    fetch: async (r: Request) => {
      if (!online) throw new Error("offline");
      return new Response(`live:${new URL(r.url).pathname}`);
    },
    URL,
    Promise,
  };
  vm.runInNewContext(await compileWorker(), ctx);
  const ask = async (path: string, mode = "cors") => {
    let out: Promise<Response> | undefined;
    listeners.fetch?.({
      request: { method: "GET", url: `https://x.test${path}`, mode },
      respondWith: (p: Promise<Response>) => {
        out = p;
      },
    });
    return out ? (await out).text() : null;
  };
  return {
    ask,
    offline: () => {
      online = false;
    },
  };
}

describe("service worker", () => {
  it("shows the last pane data and the page when the network is gone", async () => {
    const w = await loadWorker();
    expect(await w.ask("/api/data/ping")).toBe("live:/api/data/ping");
    expect(await w.ask("/", "navigate")).toBe("live:/");
    w.offline();
    expect(await w.ask("/api/data/ping")).toBe("live:/api/data/ping");
    expect(await w.ask("/holdings", "navigate")).toBe("live:/");
  });
  it("leaves sign-in and writes alone", async () => {
    const w = await loadWorker();
    expect(await w.ask("/api/auth/session")).toBeNull();
  });
});
