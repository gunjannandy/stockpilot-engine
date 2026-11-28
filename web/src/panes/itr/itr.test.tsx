import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { discoverWords } from "../../areas";
import { WordsProvider } from "../../words";
import pane, { currentFy } from "./index";

afterEach(cleanup);

describe("Tax pack pane", () => {
  it("picks the running tax year from 1 April", () => {
    expect(currentFy(new Date(2026, 2, 31))).toBe(2025);
    expect(currentFy(new Date(2026, 3, 1))).toBe(2026);
  });
  it("links the download to the pack route for the chosen year", () => {
    const words = discoverWords(
      {
        "./words/itr.en.json": {
          default: { title: "Tax pack", about: "a", year: "Tax year", download: "Get", check: "c" },
        },
      },
      "en",
    );
    render(
      <WordsProvider value={words}>
        <pane.Component />
      </WordsProvider>,
    );
    const href = screen.getByTestId("itr-download").getAttribute("href") ?? "";
    expect(href).toMatch(/^\/api\/itr\/pack\?fy=\d{4}$/);
  });
});
