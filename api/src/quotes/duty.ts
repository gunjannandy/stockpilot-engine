import type { Duty } from "../schedule/duties";
import { refreshQuotes } from "./quotes";

/** The quotes duty: every 5 minutes, in market hours only. duties.ts lists it in place of its placeholder. */
export const quotesDuty: Duty = {
  id: "quotes",
  everyMinutes: 5,
  async run(core) {
    const n = await refreshQuotes(core);
    return `refreshed ${n} quotes`;
  },
};
