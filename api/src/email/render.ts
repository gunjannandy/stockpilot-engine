// The morning email, rendered as HTML by the Worker; the Apps Script only fetches and sends it. Two versions:
// the owner's (full) and the father's (plain words, no technical lines). No Sync link in either.
export type EmailNews = {
  title: string;
  link: string;
  stocks: { symbol: string; direction: string | null }[];
};
export type EmailData = {
  date: string;
  /** The one-line call from money/src/callline, when there is one. */
  callLine?: string | null;
  mood?: string | null;
  news: EmailNews[];
  comingUp?: string[];
  changes?: string[];
  /** Until cutover: build progress and the v3 address. Until the tag: the soak counter. */
  progress?: { line: string; link?: string } | null;
  soak?: { day: number; of: number } | null;
  /** null = health could not be reached. */
  health: { ok: boolean; line: string } | null;
};

const esc = (s: string) =>
  s.replace(
    /[&<>"]/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c] as string,
  );
const MARK: Record<string, string> = { good: "▲", bad: "▼", mixed: "◆" };
const section = (title: string, body: string) => (body ? `<h2>${esc(title)}</h2>${body}` : "");
const list = (items: string[]) =>
  items.length ? `<ul>${items.map((i) => `<li>${i}</li>`).join("")}</ul>` : "";

export const HEALTH_UNREACHABLE = "Health is unreachable";

export function healthLine(h: EmailData["health"]): string {
  return h ? h.line : HEALTH_UNREACHABLE;
}

function news(d: EmailData): string {
  return list(
    d.news.map((n) => {
      const marks = n.stocks
        .map((s) => `${esc(s.symbol)} ${s.direction ? (MARK[s.direction] ?? "") : "sector news"}`)
        .join(", ");
      return `<a href="${esc(n.link)}">${esc(n.title)}</a>${marks ? ` <small>${marks}</small>` : ""}`;
    }),
  );
}

export function renderEmail(d: EmailData, who: "owner" | "father"): string {
  const owner = who === "owner";
  const parts = [
    d.callLine ? `<p><strong>${esc(d.callLine)}</strong></p>` : "",
    section("Market mood", d.mood ? `<p>${esc(d.mood)}</p>` : ""),
    section("In the news", news(d)),
    section("Coming up", list((d.comingUp ?? []).map(esc))),
    section("Since yesterday", list((d.changes ?? []).map(esc))),
    owner && d.progress
      ? section(
          "Build progress",
          `<p>${esc(d.progress.line)}${d.progress.link ? ` <a href="${esc(d.progress.link)}">Open v3</a>` : ""}</p>`,
        )
      : "",
    owner && d.soak ? section("Soak", `<p>Day ${d.soak.day} of ${d.soak.of}</p>`) : "",
    owner ? `<p><small>${esc(healthLine(d.health))}</small></p>` : "",
  ];
  return `<!doctype html><html><body style="font-family:sans-serif;max-width:640px"><h1>Morning, ${esc(d.date)}</h1>${parts.join("")}</body></html>`;
}
