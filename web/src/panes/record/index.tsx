// Record: our forecasts against the Nifty, are we adding value, our own trading, Smallcase against our own trades.
import type { Pane } from "../../areas";
import { useWords } from "../../words";
import { money } from "../_kit/data";
import { useCountUp } from "../_kit/hooks";
import { Group, GroupNav, Tile } from "../_kit/ui";

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

function Ring({ v }: { v: number }) {
  const r = 52;
  const c = 2 * Math.PI * r;
  return (
    <svg viewBox="0 0 120 120" className="rc-ring" aria-hidden="true">
      <circle cx="60" cy="60" r={r} className="rc-ring-bg" />
      <circle
        cx="60"
        cy="60"
        r={r}
        className="rc-ring-fg"
        strokeDasharray={c}
        strokeDashoffset={c * (1 - v / 100)}
        transform="rotate(-90 60 60)"
      />
    </svg>
  );
}

function Calibration() {
  const t = useWords();
  const X = (v: number) => 30 + (v / 100) * 170;
  const Y = (v: number) => 190 - (v / 100) * 170;
  return (
    <Tile title={t("v3.calibration")}>
      <svg viewBox="0 0 220 230" className="rc-cal" role="img" aria-label={t("v3.calibration")}>
        <title>{t("v3.calibration")}</title>
        {[0, 25, 50, 75, 100].map((g) => (
          <g key={g}>
            <line x1="30" x2="200" y1={Y(g)} y2={Y(g)} className="rc-grid" />
            <text x="24" y={Y(g) + 3} textAnchor="end" className="rc-ax">
              {g}
            </text>
            <text x={X(g)} y="204" textAnchor="middle" className="rc-ax">
              {g}
            </text>
          </g>
        ))}
        <line x1={X(0)} y1={Y(0)} x2={X(100)} y2={Y(100)} className="rc-diag" />
        {CAL.map((c, i) => (
          <circle
            key={c.say}
            cx={X(c.say)}
            cy={Y(c.real)}
            r="6"
            className="rc-dot"
            style={{ animationDelay: `${i * 90}ms` }}
          >
            <title>{`${c.say}% → ${c.real}%`}</title>
          </circle>
        ))}
        <text x="115" y="223" textAnchor="middle" className="rc-ax">
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
            <i className="k-grow" style={{ width: `${r.v * 5}%` }} />
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
          <div className="rc-beat">
            <Ring v={n} />
            <p className="k-big num up">{Math.round(n)}%</p>
          </div>
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
      <Tile title={t("v3.winLoss")} wide>
        <div className="rc-wl" role="img" aria-label="13 of 19 closed trades made money">
          <i className="k-grow" style={{ width: `${(13 / 19) * 100}%` }} />
        </div>
        <p className="k-note">{t("v3.winLossP")}</p>
      </Tile>
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
  return (
    <section className="rc">
      <header className="k-head">
        <p className="k-eyebrow">{t("v2.record")}</p>
        <h1>{t("v3.recordH")}</h1>
        <p>{t("v3.recordP")}</p>
      </header>
      <GroupNav
        label={t("v3.groupsNav")}
        items={[
          { id: "ours", label: t("v2.tabOurs") },
          { id: "mine", label: t("v2.tabMine") },
          { id: "sc", label: t("v2.pSc") },
        ]}
      />
      <Group id="ours" title={t("v2.tabOurs")} sub={t("v3.rcOursP")}>
        <Ours />
      </Group>
      <Group id="mine" title={t("v2.tabMine")} sub={t("v3.rcMineP")}>
        <Mine />
      </Group>
      <Group id="sc" title={t("v2.pSc")} sub={t("v3.rcScP")}>
        <Sc />
      </Group>
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
