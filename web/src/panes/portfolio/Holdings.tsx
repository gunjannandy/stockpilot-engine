// Holdings: what is owned, how many, the price, the gain, and today's call. The last synced snapshot, with its
// date: the father may skip a Sync, so the page says "as of" and never pretends the snapshot is live.
import {
  type HoldingsResponse,
  type Quote,
  type RawHolding,
  screenRoutes,
  type TodayResponse,
} from "@stockpilot/contract";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { money, pct } from "../../format";
import { NumberSlot, Pane } from "../../panekit";
import { useWords } from "../../words";
import { Seg } from "../_kit/ui";

type Scope = "all" | "kite" | "other";
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "Thu 26 Nov" from an IST time text; undefined if it is not one. */
export function asOfDay(ist: string | null | undefined): string | undefined {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(ist ?? "");
  if (!m) return undefined;
  const wd = new Date(`${m[1]}-${m[2]}-${m[3]}T00:00:00Z`).getUTCDay();
  return `${DAYS[wd]} ${Number(m[3])} ${MONTHS[Number(m[2]) - 1]}`;
}

/** The newest snapshot time among the rows (IST text compares as text), or null with none. */
export const newestSnapshot = (rows: RawHolding[]): string | null =>
  rows.reduce<string | null>((a, r) => (a === null || r.snapshot_at > a ? r.snapshot_at : a), null);

const GROUP_WORD: Record<keyof TodayResponse["groups"], string> = {
  sell: "pf.call.sell",
  weak: "pf.call.weak",
  fine_keep: "pf.call.keep",
  close_to_buy: "pf.call.buy",
  unusual: "pf.call.unusual",
};
/** Today's call for a symbol, as a words key; null when the call is not made (or not for a fund). */
export function callWord(today: TodayResponse | undefined, symbol: string): string | null {
  if (!today) return null;
  for (const g of Object.keys(GROUP_WORD) as (keyof TodayResponse["groups"])[])
    if (today.groups[g].includes(symbol)) return GROUP_WORD[g];
  return null;
}

type Line = {
  key: string;
  symbol: string;
  kind: RawHolding["kind"];
  source: string;
  qty: number;
  avg: number;
  price: number | null;
  prev: number | null;
};
const get = async <T,>(path: string): Promise<T> => {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path} ${r.status}`);
  return (await r.json()) as T;
};

function Table({ rows }: { rows: RawHolding[] }) {
  const t = useWords();
  const [scope, setScope] = useState<Scope>("all");
  const symbols = [...new Set(rows.filter((r) => r.kind === "stock").map((r) => r.symbol))];
  // Prices and calls are extras: if they fail the table still shows what is owned.
  const quotes = useQuery({
    queryKey: ["holdings", "quotes", symbols.join(",")],
    queryFn: () =>
      get<{ quotes: Quote[] }>(`/api/quotes?symbols=${encodeURIComponent(symbols.join(","))}`),
    enabled: symbols.length > 0,
    retry: false,
  });
  const today = useQuery({
    queryKey: ["holdings", "today"],
    queryFn: () => get<TodayResponse>("/api/today"),
    retry: false,
  });
  const price = new Map((quotes.data?.quotes ?? []).map((q) => [q.symbol, q]));
  const lines: Line[] = rows
    .filter((r) => scope === "all" || (scope === "kite") === (r.source === "kite"))
    .map((r) => ({
      key: `${r.source}|${r.account}|${r.kind}|${r.symbol}`,
      symbol: r.symbol,
      kind: r.kind,
      source: r.source,
      qty: r.quantity,
      avg: r.avg_price,
      price: r.kind === "stock" ? (price.get(r.symbol)?.price ?? null) : null,
      prev: r.kind === "stock" ? (price.get(r.symbol)?.prev_close ?? null) : null,
    }));
  const value = (l: Line) => (l.price === null ? null : l.price * l.qty);
  const sorted = [...lines].sort(
    (a, b) => (value(b) ?? b.avg * b.qty) - (value(a) ?? a.avg * a.qty),
  );
  const priced = lines.filter((l) => l.price !== null);
  const totalGain = priced.reduce((a, l) => a + ((l.price ?? 0) - l.avg) * l.qty, 0);
  return (
    <>
      {priced.length > 0 ? (
        <NumberSlot
          value={<span className={totalGain >= 0 ? "up" : "dn"}>{money(totalGain, 0)}</span>}
          sentence={t("pf.gainSentence").replace("{n}", String(priced.length))}
          how={t("pf.gainHow")}
        />
      ) : null}
      <Seg
        label={t("v2.srcT")}
        value={scope}
        onChange={setScope}
        options={[
          { id: "all", label: t("v2.srcAll") },
          { id: "kite", label: t("v2.srcKite") },
          { id: "other", label: t("v2.srcSc") },
        ]}
      />
      <div className="k-scroll card pf-tablewrap">
        <table className="k-table pf-table" data-testid="holdings-table">
          <thead>
            <tr>
              <th>{t("v2.hHolding")}</th>
              <th className="r">{t("v2.lotQ")}</th>
              <th className="r">{t("pf.price")}</th>
              <th className="r">{t("v2.hGain")}</th>
              <th>{t("pf.call")}</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((l) => {
              const gain = l.price === null ? null : (l.price - l.avg) * l.qty;
              const gainPct = l.price === null || l.avg <= 0 ? null : (l.price / l.avg - 1) * 100;
              const day =
                l.price === null || l.prev === null || l.prev <= 0
                  ? null
                  : (l.price / l.prev - 1) * 100;
              const word = l.kind === "stock" ? callWord(today.data, l.symbol) : null;
              return (
                <tr key={l.key}>
                  <td>
                    <b>{l.symbol}</b>{" "}
                    <span className="k-note">
                      {l.kind === "stock" ? l.source : t(`pf.kind.${l.kind}`)}
                    </span>
                  </td>
                  <td className="r num">{l.qty}</td>
                  <td className="r num">
                    {l.price === null ? (
                      <span className="k-note">{t("pf.noPrice")}</span>
                    ) : (
                      <>
                        {money(l.price)}
                        {day === null ? null : (
                          <span className={`k-note ${day >= 0 ? "up" : "dn"}`}> {pct(day)}</span>
                        )}
                      </>
                    )}
                  </td>
                  <td className={`r num ${gain === null ? "" : gain >= 0 ? "up" : "dn"}`}>
                    {gain === null ? (
                      "—"
                    ) : (
                      <>
                        {money(gain, 0)}{" "}
                        {gainPct === null ? null : <span className="k-note">{pct(gainPct)}</span>}
                      </>
                    )}
                  </td>
                  <td>
                    {word ? (
                      <span className="k-pill">{t(word)}</span>
                    ) : (
                      <span className="k-note">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}

export function Holdings() {
  const t = useWords();
  return (
    <Pane<HoldingsResponse>
      id="holdings"
      title={t("pf.holdingsTitle")}
      route={screenRoutes.holdings}
      updatedAt={(d) => newestSnapshot(d.holdings)}
      windowHours={96}
      isEmpty={(d) => d.holdings.length === 0}
    >
      {(d) => (
        <>
          <p className="k-note" data-testid="holdings-asof">
            {t("pf.asOf")} {asOfDay(newestSnapshot(d.holdings))}
          </p>
          <Table rows={d.holdings} />
        </>
      )}
    </Pane>
  );
}
