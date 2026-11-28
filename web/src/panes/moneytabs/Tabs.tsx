// Portfolio's money tabs on made-up numbers: tax and harvest, ITR pack, RSUs, XIRR against the Nifty, risk, Nifty -10%, dividends.
import { useState } from "react";
import { useWords } from "../../words";
import { type HOLDINGS, lakh, money, pct, quote } from "../_kit/data";
import { Tile } from "../_kit/ui";
import { watch } from "../_kit/watch";

type Rows = typeof HOLDINGS;
const fill = (s: string, v: Record<string, string | number>) =>
  s.replace(/\{(\w+)\}/g, (_, k) => String(v[k] ?? ""));

export function TaxTab({ rows }: { rows: Rows }) {
  const t = useWords();
  const [asked, setAsked] = useState(false);
  const booked = 84000 + rows.length * 3200;
  const room = Math.max(0, 125000 - booked);
  const losers = rows.filter((r) => r.h.gain < 0);
  return (
    <div className="k-grid">
      <div className="k-grid c3">
        <Tile title={t("v2.pYear")}>
          <p className="k-big num">{money(booked, 0)}</p>
          <p className="k-note">{t("v3.bookedP")}</p>
        </Tile>
        <Tile title={t("v2.pRoom")}>
          <p className="k-big num up">{money(room, 0)}</p>
          <p className="k-note">{t("v2.pRoomS")}</p>
          <span className="k-bar-h gain" aria-hidden="true">
            <i style={{ width: `${Math.min(100, (booked / 125000) * 100)}%` }} />
          </span>
        </Tile>
        <Tile title={t("v3.taxDue")}>
          <p className="k-big num">{money(0, 0)}</p>
          <p className="k-note">{t("v3.taxDueP")}</p>
        </Tile>
      </div>
      <Tile title={t("v3.harvest")} wide>
        <p className="k-note">{t("v3.harvestP")}</p>
        {losers.length === 0 ? (
          <p>{t("v3.harvestNone")}</p>
        ) : (
          <ul className="k-ul">
            {losers.map((r) => (
              <li key={r.st.id}>
                {fill(t("v3.harvestLine"), {
                  n: r.st.name,
                  l: money(Math.abs(r.h.gain), 0),
                  s: money(Math.abs(r.h.gain) * 0.125, 0),
                })}
              </li>
            ))}
          </ul>
        )}
      </Tile>
      <Tile title={t("v2.pPack")} wide>
        <p className="k-note">{t("v3.packP")}</p>
        <button
          type="button"
          className="sk-btn sk-tonal"
          disabled={asked}
          onClick={() => {
            setAsked(true);
            watch.say(t("v2.packAsked"));
          }}
        >
          {asked ? t("v2.packWait") : t("v2.packBuild")}
        </button>
        <p className="k-note">{t("v2.rsuNoOrder")}</p>
      </Tile>
    </div>
  );
}

const LOTS = [
  { got: "2025-02-14", qty: 40, each: 6120, src: "rsuDoc" },
  { got: "2025-08-14", qty: 38, each: 7040, src: "rsuStmt" },
  { got: "2026-02-14", qty: 36, each: 8310, src: "rsuStmt" },
];
export function RsuTab() {
  const t = useWords();
  const price = 9480;
  const tot = LOTS.reduce((a, l) => a + l.qty * price, 0);
  const cost = LOTS.reduce((a, l) => a + l.qty * l.each, 0);
  return (
    <div className="k-grid">
      <div className="k-grid c4">
        <Tile title={t("v2.rsuShares2")}>
          <p className="k-big num">{LOTS.reduce((a, l) => a + l.qty, 0)}</p>
        </Tile>
        <Tile title={t("v2.rsuCost")}>
          <p className="k-big num">{lakh(cost)}</p>
        </Tile>
        <Tile title={t("v2.rsuWorth")}>
          <p className="k-big num">{lakh(tot)}</p>
        </Tile>
        <Tile title={t("v2.rsuProfit")}>
          <p className="k-big num up">{lakh(tot - cost)}</p>
        </Tile>
      </div>
      <p className="k-note">{t("v3.rsuPrice")}</p>
      <Tile title={t("v2.rsuLots")} wide>
        <div className="k-scroll">
          <table className="k-table">
            <thead>
              <tr>
                <th>{t("v2.rsuBought")}</th>
                <th className="r">{t("v2.rsuQty")}</th>
                <th className="r">{t("v2.rsuEach")}</th>
                <th className="r">{t("v2.rsuNow")}</th>
                <th className="r">{t("v2.rsuGain")}</th>
                <th>{t("v2.rsuTerm")}</th>
                <th>{t("v2.rsuSrc")}</th>
              </tr>
            </thead>
            <tbody>
              {LOTS.map((l) => (
                <tr key={l.got}>
                  <td>{l.got}</td>
                  <td className="r num">{l.qty}</td>
                  <td className="r num">{money(l.each, 0)}</td>
                  <td className="r num">{money(l.qty * price, 0)}</td>
                  <td className="r num up">{money(l.qty * (price - l.each), 0)}</td>
                  <td>{l.got < "2025-11-28" ? t("v2.rsuLong") : t("v3.shortTerm")}</td>
                  <td>{t(`v2.${l.src}`)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="k-note">{t("v2.rsuOld")}</p>
      </Tile>
      <Tile title={t("v2.rsuExp")} wide>
        <p className="k-note">{t("v2.rsuExpP")}</p>
        <ul className="k-ul">
          <li>
            14 Aug 2027: 34 {t("v2.rsuShares")} <span className="k-pill">{t("v2.rsuEst")}</span>
          </li>
          <li>
            14 Feb 2028: 32 {t("v2.rsuShares")} <span className="k-pill">{t("v2.rsuEst")}</span>
          </li>
        </ul>
      </Tile>
      <Tile title={t("v2.rsuTax")} wide>
        <p className="k-big num">{money(Math.round((tot - cost) * 0.125), 0)}</p>
        <p className="k-note">{t("v3.rsuTaxP")}</p>
      </Tile>
    </div>
  );
}

export function ReturnsTab({ rows }: { rows: Rows }) {
  const t = useWords();
  return (
    <div className="k-grid">
      <div className="k-grid c3">
        <Tile title={t("v3.xirrUs")}>
          <p className="k-big num up">16.2%</p>
          <p className="k-note">{t("v3.xirrP")}</p>
        </Tile>
        <Tile title={t("v3.xirrNifty")}>
          <p className="k-big num">12.1%</p>
          <p className="k-note">{t("v3.xirrSame")}</p>
        </Tile>
        <Tile title={t("v3.xirrGap")}>
          <p className="k-big num up">+4.1</p>
          <p className="k-note">{t("v3.xirrAhead")}</p>
        </Tile>
      </div>
      <Tile title={t("v3.xirrEach")} wide>
        <div className="k-scroll">
          <table className="k-table">
            <thead>
              <tr>
                <th>{t("v2.hHolding")}</th>
                <th className="r">{t("v3.xirrUs")}</th>
                <th className="r">{t("v3.xirrNifty")}</th>
                <th>{t("v3.vsN")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const x = 4 + ((r.st.seed * 13) % 30);
                const n = 11 + (r.st.seed % 4);
                return (
                  <tr key={r.st.id}>
                    <td>{r.st.name}</td>
                    <td className="r num">{x.toFixed(1)}%</td>
                    <td className="r num">{n.toFixed(1)}%</td>
                    <td>
                      <span className={`k-pill ${x >= n ? "better" : "worse"}`}>
                        {x >= n ? t("v3.ahead") : t("v3.behind")}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Tile>
    </div>
  );
}

function BarList({ items }: { items: { k: string; v: number }[] }) {
  const t = useWords();
  return (
    <div className="k-barlist">
      {items.map((i) => (
        <div key={i.k} className="k-barrow">
          <span>{i.k}</span>
          <span className={`k-bar-h ${i.v > 20 ? "loss" : ""}`}>
            <i style={{ width: `${Math.min(100, i.v * 2.5)}%` }} />
          </span>
          <b className="num">{i.v.toFixed(1)}%</b>
          {i.v > 20 ? <span className="k-pill worse">{t("v3.heavy")}</span> : null}
        </div>
      ))}
    </div>
  );
}
export function RiskTab({ rows }: { rows: Rows }) {
  const t = useWords();
  const total = rows.reduce((a, r) => a + r.h.value, 0);
  const sectors = new Map<string, number>();
  for (const r of rows)
    sectors.set(r.st.sector, (sectors.get(r.st.sector) ?? 0) + (r.h.value / total) * 100);
  const down = rows.map((r) => ({ r, loss: r.h.value * 0.1 * (0.7 + (r.st.seed % 7) / 10) }));
  const sum = down.reduce((a, d) => a + d.loss, 0);
  return (
    <div className="k-grid">
      <div className="k-grid c2">
        <Tile title={t("v3.byStock")}>
          <BarList
            items={[...rows]
              .sort((a, b) => b.h.share - a.h.share)
              .slice(0, 6)
              .map((r) => ({ k: r.st.name, v: r.h.share }))}
          />
        </Tile>
        <Tile title={t("v3.bySector")}>
          <BarList items={[...sectors].sort((a, b) => b[1] - a[1]).map(([k, v]) => ({ k, v }))} />
        </Tile>
      </div>
      <Tile title={t("v3.niftyDown")} wide>
        <p className="k-big num dn">−{money(Math.round(sum), 0)}</p>
        <p className="k-note">
          {fill(t("v3.niftyDownP"), { p: ((sum / total) * 100).toFixed(1) })}
        </p>
        <div className="k-scroll">
          <table className="k-table">
            <thead>
              <tr>
                <th>{t("v2.hHolding")}</th>
                <th className="r">{t("v3.mightLose")}</th>
              </tr>
            </thead>
            <tbody>
              {down
                .sort((a, b) => b.loss - a.loss)
                .slice(0, 5)
                .map((d) => (
                  <tr key={d.r.st.id}>
                    <td>{d.r.st.name}</td>
                    <td className="r num dn">−{money(Math.round(d.loss), 0)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </Tile>
    </div>
  );
}

const EVENTS = [
  { d: "2026-12-03", id: "echo-bank", kind: "dividend", per: 14 },
  { d: "2026-12-12", id: "harbor-ports", kind: "result", per: 0 },
  { d: "2027-01-09", id: "delta-power", kind: "bonus", per: 0 },
  { d: "2027-01-22", id: "indigo-cement", kind: "dividend", per: 55 },
  { d: "2027-02-05", id: "gamma-tech", kind: "split", per: 0 },
];
export function DividendsTab({ rows }: { rows: Rows }) {
  const t = useWords();
  const qty = (id: string) => rows.find((r) => r.st.id === id)?.h.qty ?? 0;
  const cash = EVENTS.reduce((a, e) => a + e.per * qty(e.id), 0);
  return (
    <div className="k-grid">
      <Tile title={t("v3.cashSoon")}>
        <p className="k-big num up">{money(cash, 0)}</p>
        <p className="k-note">{t("v3.cashSoonP")}</p>
      </Tile>
      <Tile title={t("v3.calendar")} wide>
        <ul className="k-ul k-cal">
          {EVENTS.filter((e) => qty(e.id) > 0).map((e) => (
            <li key={e.d}>
              <b className="num">{e.d}</b>
              <span>{rows.find((r) => r.st.id === e.id)?.st.name}</span>
              <span className="k-pill">{t(`v3.ev.${e.kind}`)}</span>
              <span className="num">
                {e.per > 0
                  ? `${money(e.per * qty(e.id), 0)} (${qty(e.id)} × ${money(e.per, 0)})`
                  : ""}
              </span>
            </li>
          ))}
        </ul>
      </Tile>
    </div>
  );
}
export { pct, quote };
