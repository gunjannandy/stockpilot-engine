// The same app on Node and SQLite: docker compose, and the smoke that proves we are not locked
// to one host (story 145). Serves the web build when there is one.
import { existsSync } from "node:fs";
import { serve } from "@hono/node-server";
import { serveStatic } from "@hono/node-server/serve-static";
import { Hono } from "hono";
import { SqliteD1 } from "../../adapters/src/core";
import { loadRegistry, repoRoot } from "../migrate/discover";
import { createApp } from "./app";

const port = Number(process.env.PORT ?? 8787);
const db = new SqliteD1(process.env.SQLITE_PATH ?? ":memory:");
const api = createApp({
  d1: db,
  env: {
    INGEST_HMAC_KEY: process.env.INGEST_HMAC_KEY,
    HEALTH_SECRET: process.env.HEALTH_SECRET,
  },
  registry: await loadRegistry(),
  version: process.env.APP_VERSION ?? "dev",
});

const server = new Hono();
server.route("/", api);
if (existsSync(`${repoRoot}/web/dist`)) {
  server.use("*", serveStatic({ root: "./web/dist" }));
  server.get("*", serveStatic({ path: "./web/dist/index.html" }));
}
serve({ fetch: server.fetch, port, hostname: process.env.HOST ?? "127.0.0.1" }, (info) =>
  console.log(`stockpilot api on ${info.port}`),
);
