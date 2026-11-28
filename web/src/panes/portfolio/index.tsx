// Portfolio: All / Kite / Smallcase, holdings, target mix and budget, worth a look, and the money tabs.
import { useState } from "react";
import type { Pane } from "../../areas";
import { useWords } from "../../words";
import { HOLDINGS, lakh, money, pct, STOCKS, UNIVERSE } from "../_kit/data";
import { useCountUp } from "../_kit/hooks";
import { Toast } from "../_kit/Toast";
import { Seg, Tile, VChip } from "../_kit/ui";
import { watch } from "../_kit/watch";
import { DividendsTab, ReturnsTab, RiskTab, RsuTab, TaxTab } from "../moneytabs/Tabs";

type Scope = "all" | "kite" | "sc";
type Tab = "hold" | "tax" | "rsu" | "ret" | "risk" | "div";
const TARGET: Record<string, number> = {
  Banks: 20,
  IT: 15,
  Health: 10,
  Consumer: 12,
  Energy: 10,
  Auto: 8,
  Metals: 5,
  Transport: 5,
  Materials: 5,
  Retail: 4,
  Telecom: 3,
  Finance: 3,
};

function Mix({ rows }: { rows: typeof HOLDINGS }) {
  const t = useWords();
  const total = rows.reduce((a, r) => a + r.h.value, 0) || 1;
  const now = new Map<string, number>();
  for (const r of rows)
    now.set(r.st.sector, (now.get(r.st.sector) ?? 0) + (r.h.value / total) * 100);
  const [target, setTarget] = useState(TARGET);
  const [edit, setEdit] = useState(false);
  return (
    <Tile title={t("v2.pMix")} wide>
      <p className="k-note">{t("v2.setMixP")}</p>
      <div className="k-barlist">
        {Object.keys(target).map((s) => {
          const v = now.get(s) ?? 0;
          const g = target[s] ?? 0;
          return (
            <div key={s} className="k-barrow mix">
              <span>{s}</span>
              <span className="k-bar-h">
                <i style={{ width: `${Math.min(100, v * 2.5)}%` }} />
                <em style={{ left: `${Math.min(100, g * 2.5)}%` }} title={t("v2.mixTarget")} />
              </span>
              <b className="num">{v.toFixed(1)}%</b>
              {edit ? (
                <input
                  className="k-input k-num"
                  type="number"
                  min={0}
                  max={40}
                  value={g}
                  aria-label={`${s} ${t("v2.mixTarget")}`}
                  onChange={(e) => setTarget({ ...target, [s]: Number(e.target.value) })}
                />
              ) : (
                <span className={`k-note num ${v - g > 3 ? "dn" : v - g < -3 ? "up" : ""}`}>
                  {t("v2.mixTarget")} {g}%
                </span>
              )}
            </div>
          );
        })}
      </div>
      <div className="k-bar">
        <button type="button" className="sk-btn" onClick={() => setEdit(!edit)}>
          {edit ? t("v3.doneEdit") : t("v3.editMix")}
        </button>
        {edit && (
          <button
            type="button"
            className="sk-btn sk-tonal"
            onClick={() => {
              setEdit(false);
              watch.say(t("v2.approvedT"));
            }}
          >
            {t("v2.approveT")}
          </button>
        )}
        <span className="k-note">{t("v3.ownerOnly")}</span>
      </div>
    </Tile>
  );
}

function Budget() {
  const t = useWords();
  const [v, setV] = useState(184000);
  return (
    <Tile title={t("v2.setBudget")}>
      <p className="k-note">{t("v2.setBudgetP")}</p>
      <div className="k-bar">
        <input
          className="k-input"
          type="number"
          step={1000}
          value={v}
          aria-label={t("v2.setBudget")}
          onChange={(e) => setV(Number(e.target.value))}
        />
        <button
          type="button"
          className="sk-btn sk-tonal"
          onClick={() => watch.say(t("v2.budgetSet"))}
        >
          {t("v2.change")}
        </button>
      </div>
      <p className="k-note">{t("v3.ownerOnly")}</p>
    </Tile>
  );
}

function Opp({ rows }: { rows: typeof HOLDINGS }) {
  const t = useWords();
  const sectors = new Set(rows.map((r) => r.st.sector));
  const ideas = UNIVERSE.filter(
    (s) => s.verdict === "buy" && !rows.some((r) => r.st.id === s.id),
  ).slice(0, 3);
  return (
    <Tile title={t("v2.pOpp")}>
      <ul className="k-ul">
        {ideas.map((s) => (
          <li key={s.id}>
            <b>{s.name}</b> <VChip v={s.verdict} />{" "}
            <span className="k-note">
              {sectors.has(s.sector) ? t("v3.addsMore") : t("v3.fillsGap").replace("{s}", s.sector)}
            </span>
          </li>
        ))}
      </ul>
    </Tile>
  );
}

function PortfolioScreen() {
  const t = useWords();
  const [scope, setScope] = useState<Scope>("all");
  const [tab, setTab] = useState<Tab>("hold");
  const rows = HOLDINGS.filter(
    (r) => scope === "all" || (scope === "kite") === (r.h.account === "Kite"),
  );
  const value = rows.reduce((a, r) => a + r.h.value, 0);
  const cost = rows.reduce((a, r) => a + r.h.cost, 0);
  const shown = useCountUp(value);
  const total = value || 1;
  return (
    <section className="pf">
      <header className="k-head">
        <p className="k-eyebrow">{t("v2.portfolio")}</p>
        <h1>{lakh(Math.round(shown))}</h1>
        <p>
          {t("v2.pGain")}:{" "}
          <b className={`num ${value >= cost ? "up" : "dn"}`}>
            {money(value - cost, 0)} ({pct((value / (cost || 1) - 1) * 100)})
          </b>
        </p>
      </header>
      <div className="k-bar">
        <Seg
          label={t("v2.srcT")}
          value={scope}
          onChange={setScope}
          options={[
            { id: "all", label: t("v2.srcAll") },
            { id: "kite", label: t("v2.srcKite") },
            { id: "sc", label: t("v2.srcSc") },
          ]}
        />
        <span className="k-note">{t("v3.scopeNote")}</span>
      </div>
      <div className="k-seg k-tabs" role="tablist">
        {(["hold", "tax", "rsu", "ret", "risk", "div"] as Tab[]).map((x) => (
          <button
            key={x}
            type="button"
            role="tab"
            aria-selected={tab === x}
            onClick={() => setTab(x)}
          >
            {t(`v3.tab.${x}`)}
          </button>
        ))}
      </div>
      <div className="k-in" key={tab}>
        {tab === "hold" && (
          <div className="k-grid">
            <Tile title={t("v3.noteT")} wide>
              <p>{t("v3.noteBody")}</p>
              <p className="k-note">{t("v3.noteWhen")}</p>
            </Tile>
            <Tile title={t("v2.pHold")} wide>
              <div className="k-scroll">
                <table className="k-table">
                  <thead>
                    <tr>
                      <th>{t("v2.hHolding")}</th>
                      <th className="r">{t("v2.hValue")}</th>
                      <th className="r">{t("v2.hGain")}</th>
                      <th className="r">{t("v2.hShare")}</th>
                      <th>{t("v2.hHeld")}</th>
                      <th>{t("v2.lots")}</th>
                      <th className="r">{t("v2.lotQ")}</th>
                      <th className="r">{t("v2.lotC")}</th>
                      <th>{t("v2.lotLT")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.st.id}>
                        <td>
                          <b>{r.st.name}</b> <VChip v={r.st.verdict} />
                        </td>
                        <td className="r num">{money(r.h.value, 0)}</td>
                        <td className={`r num ${r.h.gain >= 0 ? "up" : "dn"}`}>
                          {money(r.h.gain, 0)} <span className="k-note">{pct(r.h.gainPct)}</span>
                        </td>
                        <td className="r num">{((r.h.value / total) * 100).toFixed(1)}%</td>
                        <td>
                          <span className={`k-pill ${r.h.longTerm ? "better" : ""}`}>
                            {r.h.longTerm ? t("v2.rsuLong") : t("v3.shortTerm")}
                          </span>
                        </td>
                        <td className="num">{r.h.bought}</td>
                        <td className="r num">{r.h.qty}</td>
                        <td className="r num">{money(r.h.cost, 0)}</td>
                        <td className="num">{r.h.ltFrom}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Tile>
            <div className="k-grid c2">
              <Budget />
              <Opp rows={rows} />
            </div>
            <Mix rows={rows} />
          </div>
        )}
        {tab === "tax" && <TaxTab rows={rows} />}
        {tab === "rsu" && <RsuTab />}
        {tab === "ret" && <ReturnsTab rows={rows} />}
        {tab === "risk" && <RiskTab rows={rows} />}
        {tab === "div" && <DividendsTab rows={rows} />}
      </div>
      <Toast />
      <p className="k-sample">{t("v2.proto")}</p>
    </section>
  );
}
const pane: Pane = {
  id: "portfolio",
  path: "/portfolio",
  titleKey: "shell.nav.portfolio",
  Component: PortfolioScreen,
};
export default pane;
export { STOCKS };
