import type { ProductionCheck } from "../app";

const checks: ProductionCheck[] = [
  {
    // Previews have their own database, never the production one.
    id: "C-137-1",
    async run(ctx) {
      const b = ctx.registry.buildInfo;
      if (!b?.productionDb || !b.previewDb)
        return { ok: false, detail: "database ids are not in the build" };
      return b.productionDb === b.previewDb
        ? { ok: false, detail: "previews share the production database" }
        : { ok: true, detail: "previews use their own database" };
    },
  },
  {
    // After each promotion every production check has stored a result from this run.
    id: "C-159-2",
    last: true,
    async run(ctx, run) {
      const ids = ctx.registry.areas.flatMap((a) => a.checks ?? []).map((k) => k.id);
      const rows = (await ctx.d1.prepare("select check_id, at from check_results").all())
        .results as {
        check_id: string;
        at: string;
      }[];
      const fresh = new Set(rows.filter((r) => r.at >= run.startedAt).map((r) => r.check_id));
      const missing = ids.filter((id) => id !== "C-159-2" && !fresh.has(id));
      return missing.length
        ? { ok: false, detail: `no stored result this run for ${missing.join(", ")}` }
        : { ok: true, detail: `${ids.length - 1} results stored` };
    },
  },
];
export default checks;
