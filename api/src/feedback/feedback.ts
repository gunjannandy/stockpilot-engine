// The Feedback logic, free of HTTP: opening tickets (by code, no model), following tickets, the 24-hour nudge.
import { and, eq, inArray, isNotNull, isNull, lt } from "drizzle-orm";
import { drizzle } from "drizzle-orm/d1";
import type { GithubBot } from "../../../adapters/src/github";
import * as core from "../../drizzle/core";
import { feedback } from "../../drizzle/feedback";
import { type Ctx, istText } from "../app";

export const TICKET_REPO = "stockpilot-hq/stockpilot";
export const STALE_MS = 24 * 3600_000;

type Row = typeof feedback.$inferSelect;

/** The ticket body quotes both texts: what was asked and the owner's understanding. */
export function ticketBody(row: Row): string {
  const quote = (s: string) =>
    s
      .split("\n")
      .map((l) => `> ${l}`)
      .join("\n");
  return `Opened by code from the Feedback pane. Ask ${row.id}.\n\n**What was asked**\n\n${quote(row.text)}\n\n**What we understood**\n\n${quote(row.understanding ?? "")}\n`;
}

/** Opens the ask's one ticket. A second call (or a second press) finds the number and opens nothing. */
export async function openTicket(ctx: Ctx, bot: GithubBot, id: string): Promise<number | null> {
  const [row] = await ctx.db.select().from(feedback).where(eq(feedback.id, id)).limit(1);
  if (!row || row.ticket) return row?.ticket ?? null;
  const number = await bot.openIssue({
    repo: TICKET_REPO,
    title: `Feedback: ${row.understanding?.slice(0, 80) ?? row.text.slice(0, 80)}`,
    body: ticketBody(row),
    labels: ["ready-for-agent", "feedback"],
  });
  // Only a still-empty slot is filled, so two racing presses cannot record two numbers.
  await ctx.db
    .update(feedback)
    .set({ ticket: number, updatedAt: istText(ctx.now()) })
    .where(and(eq(feedback.id, id), isNull(feedback.ticket)));
  return number;
}

/** Ticket labels -> the ask's status (story 96). Closed tickets carry `status:done`. */
export function statusFromLabels(labels: string[]): "planned" | "being_built" | "done" {
  if (labels.includes("status:done")) return "done";
  if (labels.includes("status:building") || labels.includes("status:pr")) return "being_built";
  return "planned";
}

/** One pass over the asks that have a ticket and are not finished: each status follows its ticket. */
export async function followTickets(ctx: Ctx, bot: GithubBot): Promise<number> {
  const open = await ctx.db
    .select()
    .from(feedback)
    .where(
      and(
        isNotNull(feedback.ticket),
        inArray(feedback.status, ["reviewed", "planned", "being_built"]),
      ),
    );
  let moved = 0;
  for (const row of open) {
    const status = statusFromLabels(
      await bot.labels({ repo: TICKET_REPO, issue: row.ticket as number }),
    );
    if (status === row.status) continue;
    await ctx.db
      .update(feedback)
      .set({ status, updatedAt: istText(ctx.now()) })
      .where(eq(feedback.id, row.id));
    moved++;
  }
  return moved;
}

/** An ask still `received` after 24 hours opens one issue for the owner; never a second. */
export async function nudgeStale(ctx: Ctx, bot: GithubBot): Promise<number> {
  const cutoff = istText(new Date(ctx.now().getTime() - STALE_MS));
  const stale = await ctx.db
    .select()
    .from(feedback)
    .where(
      and(
        eq(feedback.status, "received"),
        isNull(feedback.staleTicket),
        lt(feedback.createdAt, cutoff),
      ),
    );
  for (const row of stale) {
    const number = await bot.openIssue({
      repo: TICKET_REPO,
      title: "Feedback waiting for your review for 24 hours",
      body: `An ask has waited a day in the Feedback pane. Ask ${row.id}.\n\n> ${row.text.replaceAll("\n", "\n> ")}\n`,
      labels: ["ready-for-human", "feedback"],
    });
    await ctx.db
      .update(feedback)
      .set({ staleTicket: number })
      .where(and(eq(feedback.id, row.id), isNull(feedback.staleTicket)));
  }
  return stale.length;
}

/** The pieces of a request context these functions need, from a bare D1 (Jobs and tests). */
export function ctxFor(d1: unknown, now: () => Date): Ctx {
  return { db: drizzle(d1 as never, { schema: core }), now } as unknown as Ctx;
}
