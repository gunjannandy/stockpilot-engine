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

/**
 * Banner flags: a screen, or one section of it, can be put "under maintenance" by the owner in Admin.
 * `banner.<screen>` or `banner.<screen>.<section>`; true shows only the banner. A screen with no row
 * follows the release plan below; an explicit row always wins. A bannered screen bannered whole
 * hides its sections too.
 */
export const BANNER_PREFIX = "banner.";
export const bannerKey = (screen: string, section?: string) =>
  section ? `${BANNER_PREFIX}${screen}.${section}` : `${BANNER_PREFIX}${screen}`;
/** Screens that are live in the first rolling release; every other screen starts bannered. */
export const LIVE_SCREENS = ["today", "portfolio", "market", "watchlist", "stock"] as const;
/** Screens the owner needs to reach whatever the banners say, or that are plumbing: never bannered by default. */
export const ALWAYS_OPEN_SCREENS = ["admin", "signin", "sync", "ping", "more"] as const;
const OPEN: readonly string[] = [...LIVE_SCREENS, ...ALWAYS_OPEN_SCREENS];

export function isBannered(
  flags: Record<string, boolean>,
  screen: string,
  section?: string,
): boolean {
  const own = flags[bannerKey(screen)];
  const screenOn = own === undefined ? !OPEN.includes(screen) : own;
  if (screenOn || section === undefined) return screenOn;
  return flags[bannerKey(screen, section)] === true;
}
