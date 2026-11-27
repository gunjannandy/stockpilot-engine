// Small stroke icons on a 24 grid; they always sit beside a text label (no icon-only buttons).
const P: Record<string, string> = {
  today:
    "M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7z",
  worth: "M4 17l5-5 4 4 7-8M15 8h5v5",
  portfolio: "M4 8h16v11H4zM9 8V5h6v3",
  watchlist:
    "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 9.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5z",
  funds: "M12 3v18M8 7h6a3 3 0 0 1 0 6H9a3 3 0 0 0 0 6h7",
  market: "M4 5h16v14H4zM8 9h8M8 13h8M8 16h4",
  record: "M6 3h9l4 4v14H6zM14 3v5h5M9 13h7M9 17h7",
  feedback: "M4 5h16v11H9l-5 4z",
  admin:
    "M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7zM12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9L17 7M7 17l-2.1 2.1",
  more: "M5 12h.01M12 12h.01M19 12h.01",
  default: "M5 5h14v14H5z",
};
export function Icon({ name }: { name: string }) {
  return (
    <svg
      className="sh-icon"
      viewBox="0 0 24 24"
      width="22"
      height="22"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={P[name] ?? P.default} />
    </svg>
  );
}
