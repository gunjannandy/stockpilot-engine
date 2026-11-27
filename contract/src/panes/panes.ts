import { z } from "zod";
import { IstTime } from "../core/time";

/** The version of the contract this bundle was built against. A page cached in a browser one
 * version behind shows the calm "updating" state until it reloads (decisions §2 Contract). */
export const CONTRACT_VERSION = "3.0";
/** The header an answer carries its contract version in. */
export const CONTRACT_HEADER = "x-contract-version";

/** One browser error, posted by the page to /api/errors. Fields are cut to a sane size. */
export const ErrorReport = z.object({
  message: z.string().min(1).max(500),
  stack: z.string().max(4000).optional(),
  /** The pane that broke, when a pane's boundary caught it. */
  pane: z.string().max(80).optional(),
  /** Path only, never a query string. */
  url: z.string().max(300).optional(),
  version: z.string().max(80).optional(),
});
export type ErrorReport = z.infer<typeof ErrorReport>;

export const ErrorStored = z.object({ id: z.string(), at: IstTime });
export type ErrorStored = z.infer<typeof ErrorStored>;
