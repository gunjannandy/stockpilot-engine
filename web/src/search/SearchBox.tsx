// The top-bar search. `/` focuses it (Shell owns that key); typing lists matches; Enter or a click opens the stock.
import { useNavigate } from "@tanstack/react-router";
import { forwardRef, useEffect, useMemo, useState } from "react";
import { useWords } from "../words";
import { createSearch, type Entry } from "./core";

export const INDEX_URL = "/search/index.json";

export const SearchBox = forwardRef<HTMLInputElement, { entries?: Entry[] }>(function SearchBox(
  { entries: given },
  ref,
) {
  const t = useWords();
  const navigate = useNavigate();
  const [loaded, setLoaded] = useState<Entry[]>([]);
  const [q, setQ] = useState("");
  const entries = given ?? loaded;

  useEffect(() => {
    if (given) return;
    let live = true;
    fetch(INDEX_URL)
      .then((r) => (r.ok ? r.json() : []))
      .then((j) => live && Array.isArray(j) && setLoaded(j))
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [given]);

  const engine = useMemo(() => createSearch(entries), [entries]);
  const found = useMemo(() => (q.trim() ? engine.find(q) : []), [engine, q]);
  const open = (e: Entry) => {
    setQ("");
    navigate({ to: "/stock", search: { s: e.symbol } as never });
  };

  return (
    <label className="search">
      <span className="sr">{t("shell.search")}</span>
      <input
        ref={ref}
        type="search"
        value={q}
        placeholder={t("shell.search.hint")}
        onChange={(e) => setQ(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && found[0]) open(found[0]);
          if (e.key === "Escape") setQ("");
        }}
      />
      {q.trim() ? (
        <ul className="search-results" aria-label={t("search.list")}>
          {found.length === 0 ? <li className="note">{t("search.none")}</li> : null}
          {found.map((e) => (
            <li key={`${e.exchange}-${e.symbol}`}>
              <button type="button" onClick={() => open(e)}>
                <b>{e.symbol}</b> <span>{e.name}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </label>
  );
});
