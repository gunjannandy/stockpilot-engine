import { z } from "zod";
import { IstTime } from "../core/time";

/** What the father sees on each ask (story 93). `reviewed` and `not_planned` are the owner's; the rest follow the ticket. */
export const AskStatus = z.enum([
  "received",
  "reviewed",
  "planned",
  "being_built",
  "done",
  "not_planned",
]);
export type AskStatus = z.infer<typeof AskStatus>;

export const FeedbackAsk = z.object({
  id: z.string().min(1),
  text: z.string().min(1).max(2000),
  /** The owner's own words on what is wanted (story 94). */
  understanding: z.string().max(2000).nullable(),
  status: AskStatus,
  /** The ticket that builds it: its number, shown as the Job. */
  job: z.number().int().positive().nullable(),
  created_at: IstTime,
});
export type FeedbackAsk = z.infer<typeof FeedbackAsk>;

export const FeedbackList = z.object({
  asks: z.array(FeedbackAsk),
  /** Who is looking: only the owner gets the review dropdown. */
  person: z.enum(["owner", "father"]),
  updated_at: IstTime.nullable(),
});
export type FeedbackList = z.infer<typeof FeedbackList>;

export const FeedbackPost = z.object({ text: z.string().trim().min(1).max(2000) });
export type FeedbackPost = z.infer<typeof FeedbackPost>;

export const FeedbackReview = z.object({
  understanding: z.string().trim().min(1).max(2000),
  decision: z.enum(["reviewed", "not_planned"]),
});
export type FeedbackReview = z.infer<typeof FeedbackReview>;

/** One `feedback` table row as the ingest door takes it (the one-time v2 migration writes these). */
export const FeedbackRow = z.object({
  id: z.string().min(1),
  text: z.string().min(1),
  understanding: z.string().nullable(),
  status: AskStatus,
  ticket: z.number().int().positive().nullable(),
  stale_ticket: z.number().int().positive().nullable(),
  created_at: IstTime,
  reviewed_at: IstTime.nullable(),
  updated_at: IstTime,
});
export type FeedbackRow = z.infer<typeof FeedbackRow>;
