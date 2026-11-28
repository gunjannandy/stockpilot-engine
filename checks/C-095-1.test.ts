// C-095-1, C-096-1, C-097-1, C-169-2: Reviewed opens one ticket quoting both texts; the status follows the
// ticket; an ask unreviewed for 24 hours opens one issue; all by the bot, by code.

import { expect, it } from "vitest";
import { fakeGithub } from "../adapters/src/github";
import type { Ctx } from "../api/src/app";
import {
  ctxFor,
  followTickets,
  nudgeStale,
  openTicket,
  TICKET_REPO,
} from "../api/src/feedback/feedback";
import { makeApp } from "../api/src/testkit";

async function world(now: () => Date) {
  const t = await makeApp({ now });
  await t.app.request("/api/ping"); // first request applies the migrations
  const ctx = ctxFor(t.db, now);
  const bot = fakeGithub();
  const ask = async (id: string, at: string, over: Record<string, string> = {}) => {
    const r = {
      id,
      text: `text of ${id}`,
      status: "received",
      created_at: at,
      updated_at: at,
      understanding: null,
      ...over,
    };
    await t.db
      .prepare(
        "insert into feedback (id,text,status,created_at,updated_at,understanding) values (?,?,?,?,?,?)",
      )
      .bind(r.id, r.text, r.status, r.created_at, r.updated_at, r.understanding)
      .run();
  };
  const statusOf = async (id: string) =>
    (await t.db.prepare("select status from feedback where id=?").bind(id).first()) as {
      status: string;
    };
  return { ctx, bot, ask, statusOf };
}
const T0 = () => new Date("2026-11-27T10:00:00Z");

it("C-095-1 Reviewed creates one issue quoting both texts", async () => {
  const { ctx, bot, ask } = await world(T0);
  await ask("a1", "2026-11-27T15:00:00+05:30", {
    understanding: "what we understood",
    status: "reviewed",
  });
  const n1 = await openTicket(ctx, bot, "a1");
  const n2 = await openTicket(ctx, bot, "a1");
  expect(n1).toBe(n2);
  expect(bot.issues).toHaveLength(1);
  const [issue] = bot.issues;
  expect(issue?.repo).toBe(TICKET_REPO);
  expect(issue?.labels).toContain("ready-for-agent");
  expect(issue?.body).toContain("text of a1");
  expect(issue?.body).toContain("what we understood");
});

it("C-096-1 the ticket's state moves the ask's status", async () => {
  const { ctx, bot, ask, statusOf } = await world(T0);
  await ask("a2", "2026-11-27T15:00:00+05:30", { understanding: "u", status: "reviewed" });
  const n = (await openTicket(ctx, bot, "a2")) as number;
  const status = async () => (await statusOf("a2")).status;
  await followTickets(ctx, bot);
  expect(await status()).toBe("planned");
  bot.issues.find((i) => i.number === n)?.labels.push("status:building");
  await followTickets(ctx, bot);
  expect(await status()).toBe("being_built");
  bot.issues.find((i) => i.number === n)?.labels.push("status:done");
  await followTickets(ctx, bot);
  expect(await status()).toBe("done");
});

it("C-097-1 an ask unreviewed for 24 hours opens one issue", async () => {
  const { ctx, bot, ask } = await world(T0); // now = 15:30 IST on the 27th
  await ask("old", "2026-11-26T14:00:00+05:30");
  await ask("new", "2026-11-27T14:00:00+05:30");
  expect(await nudgeStale(ctx, bot)).toBe(1);
  expect(await nudgeStale(ctx, bot)).toBe(0);
  expect(bot.issues).toHaveLength(1);
});

it("C-169-2 feedback tickets are opened through the bot client only", async () => {
  const { ctx, bot, ask } = await world(T0);
  await ask("a3", "2026-11-26T09:00:00+05:30", { understanding: "u", status: "reviewed" });
  await openTicket(ctx, bot, "a3");
  await nudgeStale(ctx, bot);
  expect(bot.issues.length).toBeGreaterThan(0);
});
