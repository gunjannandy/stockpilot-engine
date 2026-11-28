// A tiny shared store so the star, "Hide for 30 days" and "Never show" agree on every screen. Star and Hide write to the API (/api/watchlist, /api/not-now); the Watchlist pane loads the saved sets.
import { useSyncExternalStore } from "react";

type S = {
  star: Set<string>;
  snooze: Set<string>;
  never: Set<string>;
  seen: Set<string>;
  toast: { text: string; undo: () => void } | null;
};
let s: S = {
  star: new Set(),
  snooze: new Set(),
  never: new Set(),
  seen: new Set(),
  toast: null,
};
const subs = new Set<() => void>();
const emit = () => {
  s = { ...s };
  for (const f of subs) f();
};
let timer: ReturnType<typeof setTimeout> | undefined;
const toast = (text: string, undo: () => void) => {
  s.toast = { text, undo };
  clearTimeout(timer);
  timer = setTimeout(() => {
    s.toast = null;
    emit();
  }, 8000);
};
let saved: () => void = () => {};
let failedText = "Could not save that. It was put back.";
/** One write to the API. A failed write puts the screen back as it was and says so. */
async function send(method: "POST" | "DELETE", url: string, body: unknown, undo: () => void) {
  try {
    const res = await fetch(url, {
      method,
      headers: body ? { "content-type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) throw new Error(String(res.status));
    saved();
  } catch {
    undo();
    s.toast = { text: failedText, undo: () => {} };
    emit();
  }
}
export const watch = {
  /** The Watchlist pane gives the saved sets, a refresh to call after a write, and the words for a failed save. */
  hydrate(star: string[], snooze: string[], onSaved: () => void, failed: string) {
    s.star = new Set(star);
    s.snooze = new Set(snooze);
    saved = onSaved;
    failedText = failed;
    emit();
  },
  toggleStar(
    id: string,
    msgOn: string,
    msgOff: string,
    name?: string,
    kind: "stock" | "fund" = "stock",
  ) {
    const was = s.star.has(id);
    was ? s.star.delete(id) : s.star.add(id);
    toast(was ? msgOff : msgOn, () => this.toggleStar(id, msgOn, msgOff, name, kind));
    emit();
    const back = () => {
      was ? s.star.add(id) : s.star.delete(id);
      emit();
    };
    if (was) void send("DELETE", `/api/watchlist/${encodeURIComponent(id)}`, null, back);
    else void send("POST", "/api/watchlist", { id, kind, ...(name ? { name } : {}) }, back);
  },
  set(kind: "snooze" | "never", id: string, on: boolean, msg?: string) {
    const had = s[kind].has(id);
    on ? s[kind].add(id) : s[kind].delete(id);
    if (kind === "snooze" && had !== on) {
      const back = () => {
        had ? s.snooze.add(id) : s.snooze.delete(id);
        emit();
      };
      if (on) void send("POST", "/api/not-now", { symbol: id, for: "month" }, back);
      else void send("DELETE", `/api/not-now/${encodeURIComponent(id)}`, null, back);
    }
    if (on && msg) toast(msg, () => this.set(kind, id, false));
    else if (!on) s.toast = null;
    emit();
  },
  say(text: string) {
    toast(text, () => {});
    emit();
  },
  markSeen(ids: string[]) {
    for (const i of ids) s.seen.add(i);
    emit();
  },
  clearToast() {
    s.toast = null;
    emit();
  },
};
export function useWatch() {
  return useSyncExternalStore(
    (f) => {
      subs.add(f);
      return () => subs.delete(f);
    },
    () => s,
  );
}
