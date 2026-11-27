import { CONTRACT_HEADER, CONTRACT_VERSION } from "@stockpilot/contract";
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { discoverWords } from "../areas";
import { CACHE_KEY, makeClient, persistClient } from "../cache/persist";
import { WordsProvider } from "../words";
import { fetchPane, PaneUpdating } from "./fetchPane";
import { freshness } from "./freshness";
import { NumberSlot, Pane, reportError, resetReports } from "./index";

const words = discoverWords(
  {
    "./words/panes.en.json": { default: (await import("../words/panes.en.json")).default },
  },
  "en",
);
type Ans = { as_of: string | null; rows: string[] };
const json = (b: unknown, h: Record<string, string> = {}, status = 200) =>
  new Response(JSON.stringify(b), {
    status,
    headers: { "content-type": "application/json", ...h },
  });

function mount(ui: React.ReactNode, client = makeClient()) {
  client.setDefaultOptions({ queries: { retry: false, gcTime: Number.POSITIVE_INFINITY } });
  return render(
    <QueryClientProvider client={client}>
      <WordsProvider value={words}>{ui}</WordsProvider>
    </QueryClientProvider>,
  );
}
const demo = (id: string, fetcher: (u: string, i?: RequestInit) => Promise<Response>) => (
  <Pane<Ans>
    id={id}
    title={id}
    path={`/api/data/${id}`}
    windowHours={24}
    fetcher={fetcher}
    updatedAt={(d) => d.as_of}
    isEmpty={(d) => d.rows.length === 0}
  >
    {(d) => (
      <ul>
        {d.rows.map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>
    )}
  </Pane>
);

afterEach(() => {
  cleanup();
  localStorage.clear();
  resetReports();
});

describe("fetchPane", () => {
  it("sends the held ETag and reuses the held answer on a 304", async () => {
    const held = { etag: '"a-1"', data: { x: 1 } };
    const f = vi.fn(async () => new Response(null, { status: 304 }));
    const got = await fetchPane("/p", held, f);
    expect(got).toBe(held);
    expect(f).toHaveBeenCalledWith("/p", { headers: { "if-none-match": '"a-1"' } });
  });
  it("raises updating on a contract version mismatch or the server's updating answer", async () => {
    await expect(
      fetchPane("/p", undefined, async () => json({}, { [CONTRACT_HEADER]: "9.9" })),
    ).rejects.toBeInstanceOf(PaneUpdating);
    await expect(
      fetchPane("/p", undefined, async () => json({ error: "updating" }, {}, 503)),
    ).rejects.toBeInstanceOf(PaneUpdating);
    const ok = await fetchPane("/p", undefined, async () =>
      json({ a: 1 }, { [CONTRACT_HEADER]: CONTRACT_VERSION, etag: '"t"' }),
    );
    expect(ok).toEqual({ etag: '"t"', data: { a: 1 } });
  });
});

describe("Pane states", () => {
  it("shows loading, then rows with the freshness chip", async () => {
    mount(demo("a", async () => json({ as_of: "2026-11-27T10:00:00+05:30", rows: ["one"] })));
    expect(screen.getByTestId("a-loading")).toBeTruthy();
    await screen.findByText("one");
    expect(screen.getByTestId("freshness").textContent).toContain("Updated");
  });
  it("shows empty", async () => {
    mount(demo("a", async () => json({ as_of: null, rows: [] })));
    await screen.findByTestId("a-empty");
  });
  it("C-019: a failed route shows its failed state and the other pane renders", async () => {
    mount(
      <>
        {demo("bad", async () => new Response("no", { status: 500 }))}
        {demo("good", async () => json({ as_of: null, rows: ["fine"] }))}
      </>,
    );
    await screen.findByTestId("bad-failed");
    await screen.findByText("fine");
  });
  it("a throwing pane body breaks alone and posts one error report", async () => {
    const post = vi.fn(async () => new Response("{}"));
    vi.stubGlobal("fetch", post);
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    mount(
      <>
        <Pane<Ans>
          id="boom"
          title="boom"
          path="/x"
          windowHours={1}
          updatedAt={() => null}
          fetcher={async () => json({ as_of: null, rows: ["r"] })}
        >
          {() => {
            throw new Error("render broke");
          }}
        </Pane>
        {demo("ok", async () => json({ as_of: null, rows: ["still here"] }))}
      </>,
    );
    await screen.findByTestId("boom-failed");
    await screen.findByText("still here");
    expect(post).toHaveBeenCalledWith("/api/errors", expect.objectContaining({ method: "POST" }));
    spy.mockRestore();
    vi.unstubAllGlobals();
  });
  it("C-022: a mismatched contract version shows the updating state", async () => {
    mount(demo("a", async () => json({ as_of: null, rows: ["x"] }, { [CONTRACT_HEADER]: "0.1" })));
    await screen.findByTestId("updating");
  });
  it("keeps the last data and says so when a refresh fails", async () => {
    const client = makeClient();
    client.setQueryData(
      ["pane", "/api/data/a"],
      {
        etag: null,
        data: { as_of: "2026-11-27T10:00:00+05:30", rows: ["kept"] },
      },
      { updatedAt: 0 },
    );
    mount(
      demo("a", async () => new Response("no", { status: 500 })),
      client,
    );
    await screen.findByText("kept");
    await screen.findByTestId("a-stale");
  });
});

describe("C-018: a second visit draws before the network answers", () => {
  it("restores the saved answer into a fresh client", async () => {
    vi.useFakeTimers();
    const first = makeClient();
    const stop = persistClient(first, localStorage);
    first.setQueryData(["pane", "/api/data/a"], {
      etag: '"e"',
      data: { as_of: null, rows: ["cached"] },
    });
    vi.advanceTimersByTime(600);
    stop();
    vi.useRealTimers();
    expect(localStorage.getItem(CACHE_KEY)).toContain("cached");

    const second = makeClient();
    persistClient(second, localStorage);
    let release: (r: Response) => void = () => {};
    const slow = () =>
      new Promise<Response>((r) => {
        release = r;
      });
    mount(demo("a", slow), second);
    expect(screen.getByText("cached")).toBeTruthy(); // drawn while the network is still pending
    release(new Response(null, { status: 304 }));
  });
  it("drops a saved cache that cannot be read", () => {
    localStorage.setItem(CACHE_KEY, "{not json");
    persistClient(makeClient(), localStorage);
    expect(localStorage.getItem(CACHE_KEY)).toBeNull();
  });
});

describe("C-172: number slot", () => {
  it("shows the value, its sentence, and opens how we worked it out", async () => {
    mount(
      <NumberSlot
        value="12.5%"
        sentence="Your gain on this stock so far."
        how="Today's price minus what you paid, over what you paid."
      />,
    );
    expect(screen.getByText("Your gain on this stock so far.")).toBeTruthy();
    const how = screen.getByText("How we worked it out");
    const details = how.closest("details") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    await userEvent.click(how);
    await waitFor(() => expect(details.open).toBe(true));
  });
});

describe("freshness", () => {
  const now = new Date("2026-11-27T12:00:00+05:30");
  it("words today, older days, and stale", () => {
    expect(freshness("2026-11-27T10:00:00+05:30", 24, now).label.key).toBe("panes.fresh.today");
    expect(freshness("2026-11-25T10:00:00+05:30", 24, now)).toMatchObject({
      stale: true,
      label: { key: "panes.fresh.on" },
    });
    expect(freshness(null, 24, now).stale).toBe(true);
    expect(freshness("2026-11-27T11:59:30+05:30", 1, now).label.key).toBe("panes.fresh.now");
  });
});

describe("reportError", () => {
  it("posts once per message", () => {
    const f = vi.fn(async () => ({}));
    reportError(new Error("same"), "p", f);
    reportError(new Error("same"), "p", f);
    expect(f).toHaveBeenCalledTimes(1);
  });
});
