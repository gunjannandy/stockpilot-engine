import type { ProductionCheck } from "../app";
import { SECRET_NAMES } from "./list";

const checks: ProductionCheck[] = [
  {
    id: "C-127-1",
    async run(ctx) {
      const res = await ctx.call("/api/secrets", {
        headers: { "x-health-secret": ctx.env.HEALTH_SECRET ?? "" },
      });
      if (res.status !== 200) return { ok: false, detail: `tracker answered ${res.status}` };
      const body = (await res.json()) as { secrets: { name: string }[] };
      const missing = SECRET_NAMES.filter((n) => !body.secrets.some((s) => s.name === n));
      return missing.length
        ? { ok: false, detail: `tracker lacks ${missing.join(", ")}` }
        : { ok: true, detail: `${body.secrets.length} secrets listed with their expiry` };
    },
  },
];
export default checks;
