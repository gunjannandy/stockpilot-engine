// The top-bar search. `/` focuses it (Shell owns that key); typing lists matches; Enter or a click opens the stock.
import { useNavigate } from "@tanstack/react-router";
import { forwardRef, useEffect, useMemo, useState } from "react";
import { UNIVERSE } from "../panes/_kit/data";
import { useWatch, watch } from "../panes/_kit/watch";
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
  const w = useWatch();
  // Preview only: with no search index file, search the made-up universe so every stock can be found and starred.
  const entries =
    given ?? (loaded.length ? loaded : UNIVERSE.map((u) => ({ symbol: u.symbol, name: u.name })));
  const idOf = (symbol: string) => UNIVERSE.find((u) => u.symbol === symbol)?.id;

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
            <li key={`${e.exchange}-${e.symbol}`} className="search-row">
              <button type="button" onClick={() => open(e)}>
                <b>{e.symbol}</b> <span>{e.name}</span>
              </button>
              {idOf(e.symbol) ? (
                <button
                  type="button"
                  className="search-star"
                  aria-pressed={w.star.has(idOf(e.symbol) as string)}
                  aria-label={t("v2.watchStar")}
                  title={t("v2.watchStar")}
                  onClick={() =>
                    watch.toggleStar(idOf(e.symbol) as string, t("v2.added"), t("v2.removed"))
                  }
                >
                  {w.star.has(idOf(e.symbol) as string) ? "★" : "☆"}
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </label>
  );
});
