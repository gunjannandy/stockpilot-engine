// Admin's switches on made-up state: Pause releases, pause per Job kind, flags, the layout editor, Recompute last N days.
import { useState } from "react";
import { useWords } from "../../words";
import { Toast } from "../_kit/Toast";
import { Tile } from "../_kit/ui";
import { watch } from "../_kit/watch";
import { Secrets } from "./Secrets";

function Switch({
  on,
  onChange,
  label,
}: {
  on: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      className="ac-sw"
      onClick={() => onChange(!on)}
    >
      <i />
    </button>
  );
}

const KINDS = ["prices", "news", "calls", "facts", "lists", "market", "backup"];
const FLAGS = [
  { id: "compare", on: true },
  { id: "exposure", on: false },
  { id: "dividends", on: true },
  { id: "rsuExpected", on: false },
];
const RAIL = [
  "today",
  "worth",
  "portfolio",
  "watchlist",
  "funds",
  "market",
  "record",
  "feedback",
  "admin",
];
const DATASETS = ["calls", "facts", "news_impact", "lists", "prices"];

export function Controls() {
  const t = useWords();
  const [paused, setPaused] = useState(false);
  const [kinds, setKinds] = useState<Record<string, boolean>>({});
  const [flags, setFlags] = useState<Record<string, boolean>>(
    Object.fromEntries(FLAGS.map((f) => [f.id, f.on])),
  );
  const [rail, setRail] = useState(RAIL.map((id) => ({ id, show: true })));
  const [ds, setDs] = useState(DATASETS[0] as string);
  const [days, setDays] = useState(30);
  const [prog, setProg] = useState<number | null>(null);
  const move = (i: number, d: number) => {
    const j = i + d;
    if (j < 0 || j >= rail.length) return;
    const n = [...rail];
    [n[i], n[j]] = [n[j] as (typeof n)[number], n[i] as (typeof n)[number]];
    setRail(n);
    watch.say(t("v3.layoutSaved"));
  };
  const recompute = () => {
    setProg(0);
    let p = 0;
    const iv = setInterval(() => {
      p += 20;
      setProg(Math.min(100, p));
      if (p >= 100) {
        clearInterval(iv);
        watch.say(t("v3.recomputed").replace("{d}", ds).replace("{n}", String(days)));
        setTimeout(() => setProg(null), 800);
      }
    }, 250);
  };
  return (
    <section className="ac">
      <h2 className="k-eyebrow">{t("v3.switches")}</h2>
      <div className={`ac-pause card ${paused ? "on" : ""}`}>
        <div>
          <h3>{t("v3.pauseRel")}</h3>
          <p className="k-note">{paused ? t("v3.pausedOn") : t("v3.pausedOff")}</p>
        </div>
        <Switch
          on={paused}
          label={t("v3.pauseRel")}
          onChange={(v) => {
            setPaused(v);
            watch.say(v ? t("v3.pausedOn") : t("v3.pausedOff"));
          }}
        />
      </div>
      <div className="k-grid c2">
        <Tile title={t("v3.pauseKind")}>
          <p className="k-note">{t("v3.pauseKindP")}</p>
          {KINDS.map((k) => (
            <div key={k} className="ac-row">
              <span>{k}</span>
              <Switch
                on={!!kinds[k]}
                label={`${t("v3.pause")} ${k}`}
                onChange={(v) => setKinds({ ...kinds, [k]: v })}
              />
            </div>
          ))}
        </Tile>
        <Tile title={t("v3.flags")}>
          <p className="k-note">{t("v3.flagsP")}</p>
          {FLAGS.map((f) => (
            <div key={f.id} className="ac-row">
              <span>
                <b>{t(`v3.flag.${f.id}`)}</b>
                <span className="k-note"> {flags[f.id] ? t("v3.flagOn") : t("v3.flagOff")}</span>
              </span>
              <Switch
                on={!!flags[f.id]}
                label={t(`v3.flag.${f.id}`)}
                onChange={(v) => setFlags({ ...flags, [f.id]: v })}
              />
            </div>
          ))}
        </Tile>
      </div>
      <div className="k-grid c2">
        <Tile title={t("v3.layout")}>
          <p className="k-note">{t("v3.layoutP")}</p>
          <ol className="ac-rail">
            {rail.map((r, i) => (
              <li key={r.id} className={r.show ? "" : "off"}>
                <span>{t(`shell.nav.${r.id}`)}</span>
                <button
                  type="button"
                  className="k-star"
                  aria-label={t("v3.moveUp")}
                  onClick={() => move(i, -1)}
                >
                  ▲
                </button>
                <button
                  type="button"
                  className="k-star"
                  aria-label={t("v3.moveDown")}
                  onClick={() => move(i, 1)}
                >
                  ▼
                </button>
                <Switch
                  on={r.show}
                  label={`${t("v3.show")} ${t(`shell.nav.${r.id}`)}`}
                  onChange={(v) =>
                    setRail(rail.map((x) => (x.id === r.id ? { ...x, show: v } : x)))
                  }
                />
              </li>
            ))}
          </ol>
        </Tile>
        <Tile title={t("v3.recompute")}>
          <p className="k-note">{t("v3.recomputeP")}</p>
          <div className="k-bar">
            <select
              className="k-input"
              value={ds}
              onChange={(e) => setDs(e.target.value)}
              aria-label={t("v3.dataset")}
            >
              {DATASETS.map((d) => (
                <option key={d}>{d}</option>
              ))}
            </select>
            <input
              className="k-input k-num"
              type="number"
              min={1}
              max={365}
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              aria-label={t("v3.lastDays")}
            />
            <span className="k-note">{t("v3.lastDays")}</span>
          </div>
          <button
            type="button"
            className="sk-btn sk-tonal"
            disabled={prog !== null}
            onClick={recompute}
          >
            {t("v3.recomputeGo")}
          </button>
          {prog !== null && (
            <span
              className="k-bar-h"
              role="progressbar"
              aria-valuenow={prog}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <i style={{ width: `${prog}%` }} />
            </span>
          )}
        </Tile>
      </div>
      <Secrets />
      <Toast />
    </section>
  );
}
