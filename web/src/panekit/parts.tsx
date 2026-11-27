import type { ReactNode } from "react";
import { useWords } from "../words";
import { fill, freshness } from "./freshness";

export function FreshnessChip({
  updatedAt,
  windowHours,
  now = new Date(),
}: {
  updatedAt: string | null | undefined;
  windowHours: number;
  now?: Date;
}) {
  const t = useWords();
  const f = freshness(updatedAt, windowHours, now);
  return (
    <span className={`chip fresh ${f.stale ? "stale" : "ok"}`} data-testid="freshness">
      {fill(t(f.label.key), f.label.vars)}
    </span>
  );
}

/** A list row with its two slots: the reason chip (why it is here) and the change mark (what moved). */
export function PaneRow({
  children,
  reason,
  change,
}: {
  children: ReactNode;
  reason?: ReactNode;
  change?: ReactNode;
}) {
  return (
    <li className="pane-row">
      <span className="row-main">{children}</span>
      {reason ? <span className="slot-reason">{reason}</span> : null}
      {change ? <span className="slot-change">{change}</span> : null}
    </li>
  );
}

/** Every number with its plain sentence and a folded "how we worked it out". */
export function NumberSlot({
  value,
  sentence,
  how,
}: {
  value: ReactNode;
  sentence: string;
  how: string;
}) {
  const t = useWords();
  return (
    <div className="number-slot" data-testid="number-slot">
      <strong className="number-value">{value}</strong>
      <p className="number-sentence">{sentence}</p>
      <details className="number-how">
        <summary>{t("panes.how")}</summary>
        <p>{how}</p>
      </details>
    </div>
  );
}
