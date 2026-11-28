// Change marks for the pane kit: the yellow mark, the newspaper icon, reason chips, the What changed
// strip with Mark all seen, and the browser-tab count. Panes pass these into PaneRow's slots.
import type { MarksAnswer } from "@stockpilot/contract";
import { useEffect } from "react";
import "./marks.css";
import { useWords } from "../../words";
import { fill } from "../freshness";

export type MarkItem = MarksAnswer["items"][number];

/** The yellow mark on a row or tab: shape and label, not colour alone. */
export function ChangeMark({ label }: { label?: string }) {
  const t = useWords();
  const text = label ?? t("marks.mark.label");
  return (
    <span
      className="change-mark"
      role="img"
      aria-label={text}
      title={text}
      data-testid="change-mark"
    />
  );
}

/** A stock in the news with no change to our call: a newspaper, never a mark. */
export function NewsIcon() {
  const t = useWords();
  return (
    <svg
      className="news-icon"
      viewBox="0 0 24 24"
      role="img"
      aria-label={t("marks.news.label")}
      data-testid="news-icon"
    >
      <title>{t("marks.news.label")}</title>
      <path d="M5 4h12a2 2 0 0 1 2 2v13H6a2 2 0 0 1-2-2V5a1 1 0 0 1 1-1Zm2 3v3h8V7H7Zm0 5v1.5h8V12H7Zm0 3v1.5h5V15H7Z" />
    </svg>
  );
}

/** One chip per reason, from the row's `reasons` field (keys under marks.reason.*, or plain text). */
export function ReasonChips({ reasons }: { reasons: string[] | undefined }) {
  const t = useWords();
  const list = reasons?.length ? reasons : [];
  return (
    <span className="reason-chips">
      {list.map((r) => {
        const key = `marks.reason.${r}`;
        const text = t(key);
        return (
          <span key={r} className="chip reason" data-testid="reason-chip">
            {text === key ? r : text}
          </span>
        );
      })}
    </span>
  );
}

const kind = (i: MarkItem) =>
  i.isNew
    ? "strip.new"
    : i.fields.some((f) => /^(call|verdict)/.test(f))
      ? "strip.call"
      : i.fields.some((f) => /chance/.test(f))
        ? "strip.chance"
        : "strip.other";

/** The strip above a list: what moved, one line each, and the one button that clears them all. */
export function WhatChangedStrip({
  items,
  nameOf = (i) => i.key,
  onOpen,
  onMarkAll,
}: {
  items: MarkItem[];
  nameOf?: (i: MarkItem) => string;
  onOpen?: (i: MarkItem) => void;
  onMarkAll: () => void;
}) {
  const t = useWords();
  const unseen = items.filter((i) => !i.seen);
  return (
    <section
      className="changed-strip"
      aria-label={t("marks.strip.title")}
      data-testid="changed-strip"
    >
      <header>
        <h2>{t("marks.strip.title")}</h2>
        {unseen.length ? (
          <button type="button" className="mark-all" onClick={onMarkAll}>
            {t("marks.markAll")}
          </button>
        ) : null}
      </header>
      {unseen.length ? (
        <ul>
          {unseen.map((i) => (
            <li key={`${i.dataset}/${i.key}`}>
              <button type="button" onClick={() => onOpen?.(i)}>
                <ChangeMark />
                <b>{nameOf(i)}</b>
                <span className="note">{t(`marks.${kind(i)}`)}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="note">{t("marks.strip.none")}</p>
      )}
    </section>
  );
}

/** The browser tab shows how many changes are waiting: "(3) stockpilot". */
export function useTabCount(unseen: number) {
  const t = useWords();
  useEffect(() => {
    const base = document.title.replace(/^\(\d+\) /, "");
    document.title = unseen > 0 ? `(${unseen}) ${base}` : base;
    return () => {
      document.title = base;
    };
  }, [unseen]);
  return unseen > 0 ? fill(t("marks.tab"), { n: String(unseen) }) : "";
}
