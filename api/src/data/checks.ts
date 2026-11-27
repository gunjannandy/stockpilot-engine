import type { ProductionCheck } from "../app";

const checks: ProductionCheck[] = [
  {
    // C-120-1: every published data file is served with immutable, year-long cache headers.
    id: "C-120-1",
    async run(ctx) {
      const files = (
        (await ctx.d1.prepare("select file from pointers where file is not null").all()) as {
          results: { file: string }[];
        }
      ).results.map((r) => r.file);
      if (files.length === 0) return { ok: true, detail: "no data files published yet" };
      const bad: string[] = [];
      for (const f of files) {
        const res = await ctx.call(`/data/${f}`);
        const cc = res.headers.get("cache-control") ?? "";
        if (res.status !== 200 || !/immutable/.test(cc) || !/max-age=31536000/.test(cc))
          bad.push(f);
      }
      return bad.length
        ? { ok: false, detail: `not immutable or missing: ${bad.join(", ")}` }
        : { ok: true, detail: `${files.length} data files, all immutable` };
    },
  },
];
export default checks;
