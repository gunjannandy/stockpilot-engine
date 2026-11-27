import http from "node:http";
import crypto from "node:crypto";

export class FakeKV {
  constructor() { this.m = new Map(); }
  async get(k, type) { const e = this.m.get(k); if (!e) return null; return type === "json" ? JSON.parse(e.v) : e.v; }
  async put(k, v, opts = {}) { this.m.set(k, { v, ttl: opts.expirationTtl }); }
  async delete(k) { this.m.delete(k); }
  async list({ prefix = "" } = {}) {
    return { keys: [...this.m.keys()].filter((k) => k.startsWith(prefix)).sort().map((name) => ({ name })), list_complete: true };
  }
}

// A fake Kite: login is simulated by calling the callback with a request token; data endpoints need the access token.
export async function startFakeKite({ apiKey = "key123", apiSecret = "secret456", requestToken = "reqtok", accessToken = "acc789" } = {}) {
  const calls = [];
  const data = {
    "/portfolio/holdings": [{ tradingsymbol: "SBIN", isin: "INE062A01020", quantity: 10, t1_quantity: 0, average_price: 600 }],
    "/mf/holdings": [{ tradingsymbol: "INF000A01010", quantity: 5, average_price: 50 }],
    "/trades": [{ trade_id: "t1" }],
    "/portfolio/positions": { net: [], day: [] },
    "/user/margins": { equity: { net: 1000 } },
    "/gtt/triggers": [],
  };
  const server = http.createServer((req, res) => {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      calls.push({ method: req.method, path: req.url });
      const send = (code, obj) => { res.writeHead(code, { "Content-Type": "application/json" }); res.end(JSON.stringify(obj)); };
      if (req.url === "/session/token" && req.method === "POST") {
        const p = new URLSearchParams(body);
        const checksum = crypto.createHash("sha256").update(apiKey + p.get("request_token") + apiSecret).digest("hex");
        if (p.get("api_key") === apiKey && p.get("request_token") === requestToken && p.get("checksum") === checksum) {
          return send(200, { status: "success", data: { access_token: accessToken } });
        }
        return send(403, { status: "error", message: "bad checksum" });
      }
      if (req.method !== "GET" || req.headers.authorization !== `token ${apiKey}:${accessToken}`) return send(403, { status: "error" });
      return data[req.url] !== undefined ? send(200, { status: "success", data: data[req.url] }) : send(404, { status: "error" });
    });
  });
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const base = `http://127.0.0.1:${server.address().port}`;
  return { base, calls, data, close: () => server.close(), apiKey, apiSecret, requestToken, accessToken };
}

export const ctx = (url, env, extra = {}) => ({ request: new Request(url, extra.init), env, data: extra.data ?? {}, params: extra.params ?? {} });
