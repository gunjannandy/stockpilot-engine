import { HealthResponse, PARTS } from "@stockpilot/contract";
import { heartbeats } from "../../drizzle/core";
import type { ProductionCheck } from "../app";

const checks: ProductionCheck[] = [
  {
    id: "C-121-1",
    async run(ctx) {
      const refused = await ctx.call("/api/health");
      if (refused.status !== 401)
        return { ok: false, detail: `health answered ${refused.status} without the header` };
      const res = await ctx.call("/api/health", {
        headers: { "x-health-secret": ctx.env.HEALTH_SECRET ?? "" },
      });
      if (res.status !== 200)
        return { ok: false, detail: `health answered ${res.status} with the header` };
      const body = HealthResponse.safeParse(await res.json());
      if (!body.success) return { ok: false, detail: "health body breaks the contract" };
      const missing = PARTS.filter((p) => !body.data.parts.some((x) => x.part === p));
      return missing.length
        ? { ok: false, detail: `health lacks ${missing.join(", ")}` }
        : { ok: true, detail: `${body.data.parts.length} parts, refused without the header` };
    },
  },
  {
    // Running versions match production: any part that has beaten since this version went live
    // reports this version.
    id: "C-135-1",
    async run(ctx) {
      const [live] = await ctx.d1
        .prepare("select first_seen_at from deploys where version = ?")
        .bind(ctx.version)
        .all()
        .then((r: { results: { first_seen_at: string }[] }) => r.results);
      if (!live) return { ok: false, detail: `version ${ctx.version} has no deploy record` };
      const since = (await ctx.db.select().from(heartbeats)).filter(
        (b) => b.at >= live.first_seen_at,
      );
      const off = since.filter((b) => b.version !== ctx.version);
      return off.length
        ? {
            ok: false,
            detail: `${off.map((b) => `${b.part}@${b.version}`).join(", ")} differ from ${ctx.version}`,
          }
        : { ok: true, detail: `${since.length} parts beat on ${ctx.version} since it went live` };
    },
  },
];
export default checks;
