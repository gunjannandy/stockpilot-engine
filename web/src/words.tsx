import { createContext, useContext } from "react";
import type { Lang, Words } from "./areas";

const Ctx = createContext<Words>({});
export const WordsProvider = Ctx.Provider;
/** t("area.key") gives the text, or the key itself so a missing word is visible, never blank. */
export function useWords() {
  const w = useContext(Ctx);
  return (key: string) => w[key] ?? key;
}
export type { Lang };
