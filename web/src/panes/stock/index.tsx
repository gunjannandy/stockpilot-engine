// The Stock pane: one stock, chosen by `?s=SYMBOL` (every row on Today, Holdings and Watchlist, and the search box,
// open it that way). Its sections read the API; see StockDetail.
import { useEffect, useState } from "react";
import type { Pane } from "../../areas";
import { useWords } from "../../words";
import type { StockView } from "../_kit/pending";
import { StockDetail } from "./StockDetail";
import "./stock.css";

const symbolFromUrl = () => new URLSearchParams(window.location.search).get("s")?.trim() ?? "";

/** The page body for a row picked on Today, Holdings or Watchlist: the same sections, from the API. */
export function Detail({ st }: { st: StockView; bars?: unknown; onPick?: (id: string) => void }) {
  return <StockDetail symbol={st.symbol} />;
}

export function StockPane() {
  const t = useWords();
  const [symbol, setSymbol] = useState(symbolFromUrl);
  useEffect(() => {
    const on = () => setSymbol(symbolFromUrl());
    window.addEventListener("popstate", on);
    return () => window.removeEventListener("popstate", on);
  }, []);
  return (
    <div className="sk-solo">
      {symbol ? (
        <StockDetail key={symbol} symbol={symbol} />
      ) : (
        <section className="pane" data-pane="stock">
          <h2>{t("stock.title")}</h2>
          <p className="pane-state empty" data-testid="stock-none">
            {t("stock.d.none")}
          </p>
        </section>
      )}
    </div>
  );
}

const pane: Pane = { id: "stock", path: "/stock", titleKey: "stock.title", Component: StockPane };
export default pane;
