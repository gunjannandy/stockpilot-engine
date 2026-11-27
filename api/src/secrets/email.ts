// The tracker email's body: plain English, only the secrets inside the warning window.
type Row = { name: string; expires_on: string | null; days_left: number | null };

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const days = (n: number) =>
  n < 0
    ? `ran out ${-n} day${n === -1 ? "" : "s"} ago`
    : n === 0
      ? "runs out today"
      : `${n} day${n === 1 ? "" : "s"} left`;

export const secretsEmailSubject = "A stockpilot key runs out soon";

export function secretsEmailHtml(rows: Row[], warnDays = 30): string {
  const soon = rows
    .filter((r) => r.days_left !== null && r.days_left <= warnDays)
    .sort((a, b) => (a.days_left ?? 0) - (b.days_left ?? 0));
  const items = soon
    .map(
      (r) =>
        `<li><b>${esc(r.name)}</b>: ${days(r.days_left as number)} (${esc(r.expires_on ?? "")})</li>`,
    )
    .join("");
  return `<!doctype html><html><body><p>${soon.length ? "These keys need renewing before they run out:" : "No key runs out in the next " + warnDays + " days."}</p><ul>${items}</ul><p>Tell the owner; nothing else is needed from you.</p></body></html>`;
}
