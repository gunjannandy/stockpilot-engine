// C-133-1: the summary route needs the nightly task's key; the note is written back through the API.
import { expect, it } from "vitest";
import { makeApp } from "../api/src/testkit";

const KEY = "task-key-".padEnd(32, "x");
const note = { day: "2026-11-28", text_en: "Quiet day.", text_bn: "শান্ত দিন।" };
const post = (t: Awaited<ReturnType<typeof makeApp>>, key: string | null, body: unknown) =>
  t.app.request("/api/notes/nightly", {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "content-type": "application/json", ...(key ? { "x-task-key": key } : {}) },
  });
const get = (t: Awaited<ReturnType<typeof makeApp>>, key: string | null) =>
  t.app.request("/api/summary", { headers: key ? { "x-task-key": key } : {} });

it("C-133-1 the summary route is closed without the task's key, and with a wrong one", async () => {
  const t = await makeApp({ env: { NOTE_TASK_KEY: KEY } as never });
  expect((await get(t, null)).status).toBe(401);
  expect((await get(t, "wrong")).status).toBe(401);
  expect((await get(t, KEY)).status).toBe(200);
});

it("C-133-1 with no key set on the Worker the route stays closed for everyone", async () => {
  const t = await makeApp();
  expect((await get(t, "")).status).toBe(401);
  expect((await get(t, KEY)).status).toBe(401);
});

it("C-133-1 the summary gives raw rows only (holdings, trades, actions, closes)", async () => {
  const t = await makeApp({ env: { NOTE_TASK_KEY: KEY } as never });
  const body = (await (await get(t, KEY)).json()) as Record<string, unknown>;
  expect(Object.keys(body).sort()).toEqual(["closes", "corporate_actions", "day", "holdings", "trades"]);
});

it("C-133-1 the note is written back through the API with the task's key, and read by a person", async () => {
  const t = await makeApp({ env: { NOTE_TASK_KEY: KEY } as never });
  expect((await post(t, null, note)).status).toBe(401);
  expect((await post(t, KEY, { ...note, text_bn: "Quiet." })).status).toBe(422);
  expect((await post(t, KEY, note)).status).toBe(200);
  expect((await post(t, KEY, { ...note, text_en: "Rewritten." })).status).toBe(200);
  const got = (await (await t.app.request("/api/notes/nightly")).json()) as {
    note: { text_en: string };
  };
  expect(got.note.text_en).toBe("Rewritten.");
});
