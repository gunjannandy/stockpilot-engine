// C-108-1: the owner's email HTML has every section from fixtures and no Sync link.
import { expect, it } from "vitest";
import { type EmailData, renderEmail } from "../api/src/email/render";

const data: EmailData = {
  date: "2026-11-29",
  callLine: "Call line here",
  mood: "Calm market",
  news: [
    {
      title: "Alpha profit up",
      link: "https://example.com/a",
      stocks: [
        { symbol: "ALPHA", direction: "good" },
        { symbol: "BETA", direction: null },
      ],
    },
  ],
  comingUp: ["Results on Monday"],
  changes: ["ALPHA entered the news list"],
  progress: { line: "Build 60% done", link: "https://v3.example.com" },
  soak: { day: 3, of: 14 },
  health: { ok: true, line: "Everything is running" },
};

it("C-108-1 owner's email has every section and no Sync link", () => {
  const html = renderEmail(data, "owner");
  for (const s of [
    "Call line here",
    "Market mood",
    "Calm market",
    "In the news",
    "Alpha profit up",
    "ALPHA ▲",
    "BETA sector news",
    "Coming up",
    "Results on Monday",
    "Since yesterday",
    "Build progress",
    "Open v3",
    "Soak",
    "Day 3 of 14",
    "Everything is running",
  ])
    expect(html).toContain(s);
  expect(html.toLowerCase()).not.toContain("sync");
  expect(renderEmail(data, "father")).not.toContain("Build progress");
});
