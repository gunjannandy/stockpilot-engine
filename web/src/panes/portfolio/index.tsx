// Portfolio: one scrolling page of groups (holdings, tax, RSUs, returns, risk, dividends). The All / Kite / Smallcase switch lives inside Holdings.
import { Link } from "@tanstack/react-router";
import { useState } from "react";
import type { Pane } from "../../areas";
import { useWords } from "../../words";
import { HOLDINGS, lakh, money, pct, STOCKS, UNIVERSE } from "../_kit/data";
import { useCountUp } from "../_kit/hooks";
import { TARGET } from "../_kit/plan";
import { Toast } from "../_kit/Toast";
import { Group, GroupNav, Seg, Tile, VChip } from "../_kit/ui";
import { DividendsTab, ReturnsTab, RiskTab, RsuTab, TaxTab } from "../moneytabs/Tabs";

type Scope = "all" | "kite" | "sc";
const GROUPS = ["hold", "tax", "rsu", "ret", "risk", "div"] as const;

/** Where the money sits: one strip, one slice per holding, coloured by our call. */
function Strip({ rows }: { rows: typeof HOLDINGS }) {
  const total = rows.reduce((a, r) => a + r.h.value, 0) || 1;
  return (
    <div className="pf-strip" role="img" aria-label="Share of the portfolio in each holding">
      {rows.map((r) => (
        <i
          key={r.st.id}
          className={`k-grow v-${r.st.verdict}`}
          style={{ width: `${(r.h.value / total) * 100}%` }}
          title={`${r.st.name} ${((r.h.value / total) * 100).toFixed(1)}%`}
        />
      ))}
    </div>
  );
}

/** The mix against the target, read only. The target itself is changed in Settings. */
function Mix({ rows }: { rows: typeof HOLDINGS }) {
  const t = useWords();
  const total = rows.reduce((a, r) => a + r.h.value, 0) || 1;
  const now = new Map<string, number>();
  for (const r of rows)
    now.set(r.st.sector, (now.get(r.st.sector) ?? 0) + (r.h.value / total) * 100);
  return (
    <Tile title={t("v2.pMix")} wide>
      <div className="k-barlist">
        {Object.entries(TARGET).map(([s, g]) => {
          const v = now.get(s) ?? 0;
          return (
            <div key={s} className="k-barrow mix">
              <span>{s}</span>
              <span className="k-bar-h">
                <i className="k-grow" style={{ width: `${Math.min(100, v * 2.5)}%` }} />
                <em style={{ left: `${Math.min(100, g * 2.5)}%` }} title={t("v2.mixTarget")} />
              </span>
              <b className="num">{v.toFixed(1)}%</b>
              <span className={`k-note num ${v - g > 3 ? "dn" : v - g < -3 ? "up" : ""}`}>
                {t("v2.mixTarget")} {g}%
              </span>
            </div>
          );
        })}
      </div>
      <p className="k-note">
        <Link to="/settings">{t("v3.mixInSettings")}</Link>
      </p>
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
  const [pick, setPick] = useState<string | null>(null);
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
      <GroupNav
        label={t("v3.groupsNav")}
        items={GROUPS.map((x) => ({ id: x, label: t(`v3.tab.${x}`) }))}
      />
      <Group
        id="hold"
        title={t("v2.pHold")}
        sub={t("v3.holdSub")}
        aside={
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
        }
      >
        <div className="k-grid" key={scope}>
          <Tile title={t("v3.noteT")} wide>
            <p>{t("v3.noteBody")}</p>
            <p className="k-note">{t("v3.noteWhen")}</p>
          </Tile>
          <Tile title={t("v3.whereMoney")} wide>
            <Strip rows={rows} />
            <div className="k-scroll">
              <table className="k-table pf-table">
                <thead>
                  <tr>
                    <th>{t("v2.hHolding")}</th>
                    <th className="r">{t("v2.hValue")}</th>
                    <th className="r">{t("v2.hGain")}</th>
                    <th>{t("v2.hShare")}</th>
                    <th>{t("v2.hHeld")}</th>
                    <th>{t("v2.lots")}</th>
                    <th className="r">{t("v2.lotQ")}</th>
                    <th className="r">{t("v2.lotC")}</th>
                    <th>{t("v2.lotLT")}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr
                      key={r.st.id}
                      aria-selected={pick === r.st.id}
                      onClick={() => setPick(pick === r.st.id ? null : r.st.id)}
                    >
                      <td>
                        <b>{r.st.name}</b> <VChip v={r.st.verdict} />
                      </td>
                      <td className="r num">{money(r.h.value, 0)}</td>
                      <td className={`r num ${r.h.gain >= 0 ? "up" : "dn"}`}>
                        {money(r.h.gain, 0)} <span className="k-note">{pct(r.h.gainPct)}</span>
                      </td>
                      <td className="pf-share num">
                        <span className="k-bar-h">
                          <i
                            className="k-grow"
                            style={{ width: `${(r.h.value / total) * 250}%` }}
                          />
                        </span>
                        {((r.h.value / total) * 100).toFixed(1)}%
                      </td>
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
            <Opp rows={rows} />
            <Mix rows={rows} />
          </div>
        </div>
      </Group>
      <Group id="tax" title={t("v3.tab.tax")} sub={t("v3.taxSub")}>
        <TaxTab rows={rows} />
      </Group>
      <Group id="rsu" title={t("v3.tab.rsu")} sub={t("v3.rsuSub")}>
        <RsuTab />
      </Group>
      <Group id="ret" title={t("v3.tab.ret")} sub={t("v3.retSub")}>
        <ReturnsTab rows={rows} />
      </Group>
      <Group id="risk" title={t("v3.tab.risk")} sub={t("v3.riskSub")}>
        <RiskTab rows={rows} />
      </Group>
      <Group id="div" title={t("v3.tab.div")} sub={t("v3.divSub")}>
        <DividendsTab rows={rows} />
      </Group>
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
