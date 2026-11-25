// GET /api/me → {person}, the person the session cookie names (set by _middleware).
export async function onRequestGet({ data }) {
  return new Response(JSON.stringify({ person: data.person }), {
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}
