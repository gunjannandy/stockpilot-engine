import { readOgImage } from "./og-image.mjs";

export default {
  async fetch(req) {
    const base = new URL(req.url).searchParams.get("base") || undefined;
    const t0 = Date.now();
    const image = await readOgImage(new Response(req.body, { headers: { "content-type": "text/html" } }), base);
    return Response.json({ image, wallMs: Date.now() - t0 });
  },
};
