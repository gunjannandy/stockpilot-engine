// Small stroke icons on a 24 grid; icon-only controls carry an aria-label and a title.
const P: Record<string, string> = {
  today: "M4 6h16v14H4zM4 10h16M8 3v4M16 3v4M8 14h2",
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
  settings: "M4 7h10M18 7h2M4 17h2M10 17h10M14 4v6M6 14v6",
  more: "M5 12h.01M12 12h.01M19 12h.01",
  sun: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4",
  moon: "M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z",
  default: "M5 5h14v14H5z",
};
export function Icon({ name, size = 22 }: { name: string; size?: number }) {
  return (
    <svg
      className="sh-icon"
      viewBox="0 0 24 24"
      width={size}
      height={size}
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
