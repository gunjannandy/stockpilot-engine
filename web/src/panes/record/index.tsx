// Record: our forecasts against the Nifty, are we adding value, our own trading, Smallcase against our own trades.
import { useState } from "react";
import type { Pane } from "../../areas";
import { useWords } from "../../words";
import { money } from "../_kit/data";
import { useCountUp } from "../_kit/hooks";
import { Seg, Tile } from "../_kit/ui";

type Tab = "ours" | "mine" | "sc";
const CAL = [
  { say: 30, real: 33 },
  { say: 40, real: 38 },
  { say: 50, real: 54 },
  { say: 60, real: 57 },
  { say: 70, real: 72 },
];
const MISSES = [
  {
    n: "Delta Power",
    call: "Buy at 62%",
    score: -4.1,
    why: "Results came a quarter late and the price fell before them. We did not weigh the date.",
  },
  {
    n: "Cedar Pharma",
    call: "Weak at 36%",
    score: -2.3,
    why: "The stock rose on a one-off order. Our view had no way to see that order coming.",
  },
  {
    n: "Juno Finance",
    call: "Buy at 58%",
    score: -1.2,
    why: "The whole sector fell together. The call was right on the company and wrong on the market.",
  },
];
const MONTHS = ["Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov"];
const BOOKED = [0, 18, 0, 42, 9, 0, 27, 0, 61, 0, 12, 33];

function Calibration() {
  const t = useWords();
  return (
    <Tile title={t("v3.calibration")}>
      <svg viewBox="0 0 220 220" className="rc-cal" role="img" aria-label={t("v3.calibration")}>
        <title>{t("v3.calibration")}</title>
        <line x1="20" y1="200" x2="200" y2="20" className="rc-diag" />
        {CAL.map((c) => (
          <circle
            key={c.say}
            cx={20 + (c.say / 100) * 180 * 1}
            cy={200 - (c.real / 100) * 180}
            r="6"
            className="rc-dot"
          />
        ))}
        <text x="110" y="216" textAnchor="middle" className="rc-ax">
          {t("v3.calX")}
        </text>
      </svg>
      <p className="k-note">{t("v2.calLine")}</p>
    </Tile>
  );
}

function Compare() {
  const t = useWords();
  const rows = [
    { k: "ours", v: 14.8, c: "gain" },
    { k: "nifty", v: 11.2, c: "" },
    { k: "equal", v: 12.6, c: "" },
  ];
  return (
    <Tile title={t("v3.addValue")} wide>
      <p className="k-note">{t("v3.addValueP")}</p>
      {rows.map((r) => (
        <div key={r.k} className="k-barrow rc-row">
          <span>{t(`v3.cmp.${r.k}`)}</span>
          <span className={`k-bar-h ${r.c}`} aria-hidden="true">
            <i style={{ width: `${r.v * 5}%` }} />
          </span>
          <b className="num">{r.v.toFixed(1)}%</b>
        </div>
      ))}
      <p className="rc-verdict">{t("v3.addValueSay")}</p>
    </Tile>
  );
}

function Ours() {
  const t = useWords();
  const n = useCountUp(63);
  return (
    <div className="k-grid">
      <div className="k-grid c3">
        <Tile title={t("v2.rCalls")}>
          <p className="k-big num">24</p>
          <p className="k-note">{t("v2.rCallsS")}</p>
        </Tile>
        <Tile title={t("v2.rBeat")}>
          <p className="k-big num up">{Math.round(n)}%</p>
          <p className="k-note">{t("v3.beatP")}</p>
        </Tile>
        <Tile title={t("v3.avgGap")}>
          <p className="k-big num up">+2.4</p>
          <p className="k-note">{t("v3.avgGapP")}</p>
        </Tile>
      </div>
      <div className="k-grid c2">
        <Calibration />
        <Compare />
      </div>
      <Tile title={t("v3.misses")} wide>
        <p className="k-note">{t("v3.missesP")}</p>
        {MISSES.map((m) => (
          <details key={m.n} className="rc-miss">
            <summary>
              <b>{m.n}</b> · {m.call} ·{" "}
              <span className="dn num">
                {m.score.toFixed(1)} {t("v3.pts")}
              </span>
            </summary>
            <p>{m.why}</p>
          </details>
        ))}
      </Tile>
    </div>
  );
}

function Mine() {
  const t = useWords();
  const hi = Math.max(...BOOKED);
  return (
    <div className="k-grid">
      <div className="k-grid c4">
        <Tile title={t("v2.rClosed")}>
          <p className="k-big num">19</p>
        </Tile>
        <Tile title={t("v2.rWin")}>
          <p className="k-big num up">13</p>
          <p className="k-note">{t("v3.of19")}</p>
        </Tile>
        <Tile title={t("v2.rHeldW")}>
          <p className="k-big num">5</p>
        </Tile>
        <Tile title={t("v2.rHeldL")}>
          <p className="k-big num dn">3</p>
        </Tile>
      </div>
      <Tile title={t("v2.rEarly")}>
        <p className="k-big num">4 {t("v3.of")} 11</p>
        <p className="k-note">{t("v2.rEarlyS")}</p>
      </Tile>
      <Tile title={t("v2.rMonth")} wide>
        <div className="rc-months">
          {MONTHS.map((m, i) => (
            <div key={m}>
              <span
                className="rc-bar"
                style={{ height: `${Math.max(4, ((BOOKED[i] ?? 0) / hi) * 100)}%` }}
                title={money((BOOKED[i] ?? 0) * 1000, 0)}
              />
              <span className="k-note">{m}</span>
            </div>
          ))}
        </div>
      </Tile>
    </div>
  );
}

function Sc() {
  const t = useWords();
  return (
    <div className="k-grid c2">
      <Tile title={t("v3.ourTrades")}>
        <p className="k-big num up">15.9%</p>
        <p className="k-note">{t("v3.routeP")}</p>
      </Tile>
      <Tile title={t("v3.scRoute")}>
        <p className="k-big num">12.4%</p>
        <p className="k-note">{t("v3.routeP")}</p>
      </Tile>
      <Tile title={t("v3.scSay")} wide>
        <p>{t("v3.scVerdict")}</p>
      </Tile>
    </div>
  );
}

function RecordScreen() {
  const t = useWords();
  const [tab, setTab] = useState<Tab>("ours");
  return (
    <section className="rc">
      <header className="k-head">
        <p className="k-eyebrow">{t("v2.record")}</p>
        <h1>{t("v3.recordH")}</h1>
        <p>{t("v3.recordP")}</p>
      </header>
      <div className="k-bar">
        <Seg
          label={t("v2.record")}
          value={tab}
          onChange={setTab}
          options={[
            { id: "ours", label: t("v2.tabOurs") },
            { id: "mine", label: t("v2.tabMine") },
            { id: "sc", label: t("v2.pSc") },
          ]}
        />
      </div>
      <div className="k-in" key={tab}>
        {tab === "ours" && <Ours />}
        {tab === "mine" && <Mine />}
        {tab === "sc" && <Sc />}
      </div>
      <p className="k-sample">{t("v2.proto")}</p>
    </section>
  );
}
const pane: Pane = {
  id: "record",
  path: "/record",
  titleKey: "shell.nav.record",
  Component: RecordScreen,
};
export default pane;
