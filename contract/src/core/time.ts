import { z } from "zod";

/** An instant as IST ISO text, e.g. 2026-11-25T09:15:00+05:30. */
export const IstTime = z.string().regex(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+05:30$/, "IST time");
/** A calendar date, e.g. 2026-11-25. */
export const IsoDate = z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "ISO date");
