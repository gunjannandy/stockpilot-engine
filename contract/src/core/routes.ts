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
import { FlagMap, FlagWrite, FlagWriteResponse } from "./flags";
import { HealthResponse } from "./health";
import { Heartbeat, HeartbeatAck } from "./heartbeat";
import { PingLatest, PingRow } from "./ping";
import {
  ChecksRunResponse,
  StatusResponse,
  WhatsNewList,
  WhatsNewPost,
  WhatsNewStored,
} from "./status";

export type Route = {
  method: "GET" | "POST";
  path: string;
  /** person: a signed-in reader; ingest: Jobs and workflows (HMAC); secret: the health header; public: no secret, no data. */
  auth: "person" | "ingest" | "secret" | "public";
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
  health: route({
    method: "GET",
    path: "/api/health",
    auth: "secret",
    request: none,
    response: HealthResponse,
  }),
  status: route({
    method: "GET",
    path: "/api/status",
    auth: "public",
    request: none,
    response: StatusResponse,
  }),
  flags_read: route({
    method: "GET",
    path: "/api/flags",
    auth: "person",
    request: none,
    response: FlagMap,
  }),
  flag_write: route({
    method: "POST",
    path: "/api/flags",
    auth: "secret",
    request: FlagWrite,
    response: FlagWriteResponse,
  }),
  checks_run: route({
    method: "POST",
    path: "/api/checks/run",
    auth: "ingest",
    request: none,
    response: ChecksRunResponse,
  }),
  whatsnew_post: route({
    method: "POST",
    path: "/api/whatsnew",
    auth: "ingest",
    request: WhatsNewPost,
    response: WhatsNewStored,
  }),
  whatsnew_read: route({
    method: "GET",
    path: "/api/whatsnew",
    auth: "person",
    request: none,
    response: WhatsNewList,
  }),
} as const;
export type RouteId = keyof typeof routes;
