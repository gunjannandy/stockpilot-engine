import { z } from "zod";
import {
  IngestRequest,
  IngestResponse,
  JobFinishRequest,
  JobFinishResponse,
  JobStartRequest,
  JobStartResponse,
  MarketStatus,
} from "./door";
import { Heartbeat, HeartbeatAck } from "./heartbeat";
import { PingLatest, PingRow } from "./ping";

export type Route = {
  method: "GET" | "POST";
  path: string;
  auth: "person" | "ingest";
  request: z.ZodType;
  response: z.ZodType;
};
const route = <R extends Route>(r: R): R => r;
const none = z.object({});

/** Every core route. SKELAPI serves them; the web client and the Python io layer are generated
 * from this table, so a route nobody lists here does not exist for them. */
export const routes = {
  ping_press: route({
    method: "POST",
    path: "/api/ping",
    auth: "person",
    request: none,
    response: PingRow,
  }),
  ping_latest: route({
    method: "GET",
    path: "/api/ping",
    auth: "person",
    request: none,
    response: PingLatest,
  }),
  ingest_write: route({
    method: "POST",
    path: "/api/ingest",
    auth: "ingest",
    request: IngestRequest,
    response: IngestResponse,
  }),
  job_start: route({
    method: "POST",
    path: "/api/jobs/start",
    auth: "ingest",
    request: JobStartRequest,
    response: JobStartResponse,
  }),
  job_finish: route({
    method: "POST",
    path: "/api/jobs/finish",
    auth: "ingest",
    request: JobFinishRequest,
    response: JobFinishResponse,
  }),
  market_status: route({
    method: "GET",
    path: "/api/market/status",
    auth: "ingest",
    request: none,
    response: MarketStatus,
  }),
  heartbeat_write: route({
    method: "POST",
    path: "/api/heartbeat",
    auth: "ingest",
    request: Heartbeat,
    response: HeartbeatAck,
  }),
} as const;
export type RouteId = keyof typeof routes;
