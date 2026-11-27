import { describe, expect, it } from "vitest";
import { discoverPanes, discoverWords } from "./areas";
import pingPane from "./panes/ping";

const stub = (id: string) => ({
  default: { id, path: `/${id}`, titleKey: `${id}.title`, Component: () => null },
});

describe("discovery by folder", () => {
  it("orders panes by folder and needs no registration", () => {
    const panes = discoverPanes({
      "./panes/zeta/index.tsx": stub("zeta"),
      "./panes/alpha/index.tsx": stub("alpha"),
    });
    expect(panes.map((p) => p.id)).toEqual(["alpha", "zeta"]);
  });
  it("namespaces each words file by its area and picks one language", () => {
    const w = discoverWords(
      {
        "./words/ping.en.json": { default: { title: "Ping" } },
        "./words/ping.bn.json": { default: { title: "পিং" } },
      },
      "bn",
    );
    expect(w).toEqual({ "ping.title": "পিং" });
  });
  it("finds the real ping pane and ships both languages for it", async () => {
    const en = (await import("./words/ping.en.json")).default;
    const bn = (await import("./words/ping.bn.json")).default;
    expect(Object.keys(bn).sort()).toEqual(Object.keys(en).sort());
    expect(pingPane.id).toBe("ping");
  });
});
