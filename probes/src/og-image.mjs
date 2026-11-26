// Reads the og:image address from a page, streaming, so a Pages Function stays inside its CPU budget.
// Needs HTMLRewriter (a workerd global), so it only runs in Workers and Pages Functions.
export async function readOgImage(response, pageUrl) {
  let found = null;
  const rewriter = new HTMLRewriter().on("meta", {
    element(el) {
      if (found) return;
      const key = (el.getAttribute("property") || el.getAttribute("name") || "").toLowerCase();
      if (key !== "og:image") return;
      const raw = el.getAttribute("content");
      if (!raw) return;
      try {
        const u = new URL(raw, pageUrl || undefined);
        if (u.protocol === "http:" || u.protocol === "https:") found = u.href;
      } catch { /* not a usable address */ }
    },
  });
  // Draining the transformed body is what runs the handlers.
  await rewriter.transform(response).arrayBuffer();
  return found;
}
