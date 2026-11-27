import { z } from "zod";

/** Flag keys with a meaning the platform itself reads. Any other key is a pane's own flag. */
export const PAUSE_RELEASES = "pause_releases";

export const FlagMap = z.object({ flags: z.record(z.string(), z.boolean()) });
export type FlagMap = z.infer<typeof FlagMap>;
export const FlagWrite = z.object({
  key: z.string().regex(/^[a-z][a-z0-9_.-]*$/),
  enabled: z.boolean(),
});
export const FlagWriteResponse = z.object({ key: z.string(), enabled: z.boolean() });

/** A flagged pane is hidden until its flag is switched on; an unflagged pane is always shown. */
export function paneVisible(pane: { flag?: string }, flags: Record<string, boolean>): boolean {
  return pane.flag === undefined || flags[pane.flag] === true;
}
