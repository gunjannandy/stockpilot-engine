// Theme, text size and language are per-device choices: kept in localStorage, applied to <html>
// before the first paint so a reload never flashes. Storage can be blocked; the page still works.
export type ThemeChoice = "auto" | "light" | "dark";
export type SizeChoice = "normal" | "large" | "xlarge";
export type LangChoice = "en" | "bn";

const KEYS = { theme: "sp.theme", size: "sp.size", lang: "sp.lang" } as const;
const THEMES: ThemeChoice[] = ["auto", "light", "dark"];
const SIZES: SizeChoice[] = ["normal", "large", "xlarge"];
const LANGS: LangChoice[] = ["en", "bn"];

function read<T extends string>(key: string, allowed: T[], fallback: T): T {
  try {
    const v = localStorage.getItem(key);
    return allowed.includes(v as T) ? (v as T) : fallback;
  } catch {
    return fallback;
  }
}
function write(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* blocked storage: the choice lasts until reload */
  }
}

export const getTheme = () => read(KEYS.theme, THEMES, "auto");
export const getSize = () => read(KEYS.size, SIZES, "normal");
export const getLang = (): LangChoice =>
  read(KEYS.lang, LANGS, navigator.language.startsWith("bn") ? "bn" : "en");

export function applyTheme(t: ThemeChoice, root: HTMLElement = document.documentElement) {
  if (t === "auto") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", t);
}
export function applySize(s: SizeChoice, root: HTMLElement = document.documentElement) {
  if (s === "normal") root.removeAttribute("data-size");
  else root.setAttribute("data-size", s);
}
export function setTheme(t: ThemeChoice) {
  write(KEYS.theme, t);
  applyTheme(t);
}
export function setSize(s: SizeChoice) {
  write(KEYS.size, s);
  applySize(s);
}
export function setLang(l: LangChoice) {
  write(KEYS.lang, l);
  document.documentElement.lang = l;
}
/** Call once, before render. */
export function applyStored() {
  applyTheme(getTheme());
  applySize(getSize());
  document.documentElement.lang = getLang();
}
