import type { ProductionCheck } from "../app";

const checks: ProductionCheck[] = [
  {
    id: "C-119-2",
    async run(ctx) {
      const res = await ctx.call("/api/monitor");
      if (res.status !== 200) return { ok: false, detail: `monitor answered ${res.status}` };
      const m = (await res.json()) as Record<string, unknown>;
      if (typeof m.d1_bytes !== "number" || m.d1_bytes <= 0)
        return { ok: false, detail: "monitor has no D1 size" };
      if (typeof m.d1_reads !== "number" || typeof m.d1_writes !== "number")
        return { ok: false, detail: "monitor lacks daily reads or writes" };
      return {
        ok: true,
        detail: `D1 ${m.d1_bytes} bytes, ${m.d1_reads} reads, ${m.d1_writes} writes today`,
      };
    },
  },
];
export default checks;
