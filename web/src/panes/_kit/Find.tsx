// A fuzzy find box over every stock we analyse (typos fine). The lists show the top ones only; this reaches the rest.
import { useNavigate } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { createSearch } from "../../search/core";
import { useWords } from "../../words";
import { UNIVERSE } from "./pending";

export function Find({
  placeholder,
  onPick,
  skip,
  actionLabel,
}: {
  placeholder: string;
  /** Without this, a pick opens the stock page. */
  onPick?: (id: string) => void;
  skip?: (id: string) => boolean;
  actionLabel?: string;
}) {
  const t = useWords();
  const go = useNavigate();
  const [q, setQ] = useState("");
  const engine = useMemo(
    () =>
      createSearch(
        UNIVERSE.map((s) => ({ symbol: s.symbol, name: s.name })),
        6,
      ),
    [],
  );
  const hits = useMemo(() => {
    if (!q.trim()) return [];
    const by = new Map(UNIVERSE.map((s) => [s.symbol, s]));
    return engine
      .find(q)
      .map((e) => by.get(e.symbol))
      .filter((s): s is (typeof UNIVERSE)[number] => !!s && !skip?.(s.id));
  }, [engine, q, skip]);
  const pick = (s: (typeof UNIVERSE)[number]) => {
    setQ("");
    if (onPick) onPick(s.id);
    else go({ to: "/stock", search: { s: s.symbol } as never });
  };
  return (
    <div className="wl-add">
      <input
        className="k-input"
        type="search"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && hits[0]) pick(hits[0]);
          if (e.key === "Escape") setQ("");
        }}
        placeholder={placeholder}
        aria-label={placeholder}
      />
      {q.trim() ? (
        <ul className="wl-hits k-in">
          {hits.length === 0 ? <li className="k-note">{t("search.none")}</li> : null}
          {hits.map((s) => (
            <li key={s.id}>
              <button type="button" onClick={() => pick(s)}>
                <b>{s.name}</b>{" "}
                <span className="k-note">
                  {s.symbol} · {s.sector}
                </span>
                {actionLabel ? <span className="k-link">＋ {actionLabel}</span> : null}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
