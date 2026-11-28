// A tiny shared store so the star, "Hide for 30 days" and "Never show" agree on every screen. Prototype only: nothing is saved.
import { useSyncExternalStore } from "react";

type S = {
  star: Set<string>;
  snooze: Set<string>;
  never: Set<string>;
  seen: Set<string>;
  toast: { text: string; undo: () => void } | null;
};
let s: S = {
  star: new Set(["echo-bank", "gamma-tech", "juno-finance", "harbor-ports"]),
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
export const watch = {
  toggleStar(id: string, msgOn: string, msgOff: string) {
    const was = s.star.has(id);
    was ? s.star.delete(id) : s.star.add(id);
    toast(was ? msgOff : msgOn, () => this.toggleStar(id, msgOn, msgOff));
    emit();
  },
  set(kind: "snooze" | "never", id: string, on: boolean, msg?: string) {
    on ? s[kind].add(id) : s[kind].delete(id);
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
