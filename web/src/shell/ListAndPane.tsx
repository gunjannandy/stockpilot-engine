// The list-and-pane frame. The list column scrolls on its own, the pane stays put beside it.
// Arrows step the selection, Esc goes back; on a phone the list and the full page take turns.
import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { useWords } from "../words";

export type Row = { id: string; group?: string; groupLabel?: string };

function selFromUrl(): string | null {
  return new URLSearchParams(window.location.search).get("s");
}

export function ListAndPane<T extends Row>(props: {
  items: T[];
  renderRow: (item: T) => ReactNode;
  renderPane: (item: T) => ReactNode;
  label: string;
}) {
  const { items, renderRow, renderPane, label } = props;
  const t = useWords();
  const [sel, setSel] = useState<string | null>(selFromUrl);
  const [open, setOpen] = useState(() => selFromUrl() !== null);
  const listRef = useRef<HTMLDivElement>(null);
  const current = items.find((i) => i.id === sel) ?? items[0];

  const choose = useCallback((id: string, opts?: { open?: boolean; push?: boolean }) => {
    setSel(id);
    if (opts?.open) setOpen(true);
    const url = new URL(window.location.href);
    url.searchParams.set("s", id);
    if (opts?.push) window.history.pushState({}, "", url);
    else window.history.replaceState({}, "", url);
  }, []);

  useEffect(() => {
    const onPop = () => {
      setSel(selFromUrl());
      setOpen(selFromUrl() !== null);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      const typing = el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA");
      if (e.key === "Escape") {
        if (typing) (el as HTMLElement).blur();
        if (open) {
          setOpen(false);
          window.history.back();
        }
        listRef.current?.querySelector<HTMLElement>('[aria-current="true"]')?.focus();
        return;
      }
      if (typing || (e.key !== "ArrowDown" && e.key !== "ArrowUp")) return;
      e.preventDefault();
      const i = items.findIndex((x) => x.id === current?.id);
      const next =
        items[Math.max(0, Math.min(items.length - 1, i + (e.key === "ArrowDown" ? 1 : -1)))];
      if (!next) return;
      choose(next.id);
      requestAnimationFrame(() => {
        const row = listRef.current?.querySelector<HTMLElement>(`[data-id="${next.id}"]`);
        row?.focus({ preventScroll: true });
        row?.scrollIntoView({ block: "nearest" });
      });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [items, current, open, choose]);

  let lastGroup: string | undefined;
  return (
    <div className="lp" data-open={open ? "pane" : "list"}>
      <nav className="lp-list" ref={listRef} aria-label={label}>
        {items.map((it) => {
          const header = it.group !== lastGroup && it.groupLabel;
          lastGroup = it.group;
          return (
            <div key={it.id} className="lp-item">
              {header ? <div className="lp-group">{it.groupLabel}</div> : null}
              <button
                type="button"
                className="lp-row"
                data-id={it.id}
                aria-current={current?.id === it.id ? "true" : undefined}
                onClick={() => choose(it.id, { open: true, push: true })}
              >
                {renderRow(it)}
              </button>
            </div>
          );
        })}
      </nav>
      <section className="lp-pane" aria-label={t("shell.pane.label")}>
        <button
          type="button"
          className="lp-back"
          onClick={() => {
            setOpen(false);
            window.history.back();
          }}
        >
          ← {t("shell.pane.back")}
        </button>
        {current ? renderPane(current) : null}
        <p className="note lp-keys">{t("shell.keys")}</p>
      </section>
    </div>
  );
}
