// Browser errors go to /api/errors, once per distinct message per page load, at most 20 a load.
import { CONTRACT_VERSION, type ErrorReport } from "@stockpilot/contract";

const seen = new Set<string>();
const LIMIT = 20;

export function resetReports() {
  seen.clear();
}

export function reportError(
  err: unknown,
  pane?: string,
  fetcher: (u: string, i?: RequestInit) => Promise<unknown> = (u, i) => fetch(u, i),
): void {
  const e = err instanceof Error ? err : new Error(String(err));
  const message = (e.message || "error").slice(0, 500);
  const key = `${pane ?? ""}|${message}`;
  if (seen.has(key) || seen.size >= LIMIT) return;
  seen.add(key);
  const report: ErrorReport = {
    message,
    stack: e.stack?.slice(0, 4000),
    pane,
    url: typeof location === "undefined" ? undefined : location.pathname,
    version: CONTRACT_VERSION,
  };
  try {
    void Promise.resolve(
      fetcher("/api/errors", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(report),
      }),
    ).catch(() => {});
  } catch {
    // Reporting must never raise an error of its own.
  }
}

/** Catches what no pane boundary does: script errors and unhandled promise rejections. */
export function installErrorReporting(target: Window = window): () => void {
  const onError = (ev: ErrorEvent) => reportError(ev.error ?? ev.message);
  const onRejection = (ev: PromiseRejectionEvent) => reportError(ev.reason);
  target.addEventListener("error", onError);
  target.addEventListener("unhandledrejection", onRejection);
  return () => {
    target.removeEventListener("error", onError);
    target.removeEventListener("unhandledrejection", onRejection);
  };
}
