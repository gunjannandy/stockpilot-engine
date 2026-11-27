import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { WordsProvider } from "../../words";
import bn from "../../words/signin.bn.json";
import en from "../../words/signin.en.json";
import pane from "./index";

afterEach(cleanup);
const prefix = (w: Record<string, string>) =>
  Object.fromEntries(Object.entries(w).map(([k, v]) => [`signin.${k}`, v]));

describe("Sign-in pane", () => {
  it("is a form that posts the address to /login, in either language", () => {
    for (const words of [en, bn]) {
      render(
        <WordsProvider value={prefix(words)}>
          <pane.Component />
        </WordsProvider>,
      );
      const box = screen.getByLabelText(words.email) as HTMLInputElement;
      expect(box.type).toBe("email");
      expect(box.form?.getAttribute("action")).toBe("/login");
      expect(box.form?.getAttribute("method")).toBe("post");
      cleanup();
    }
  });
  it("ships the same words in both languages", () => {
    expect(Object.keys(bn).sort()).toEqual(Object.keys(en).sort());
  });
});
