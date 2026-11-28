// Settings: the owner's plan. Money left this month, the monthly budget, and the target mix. Nothing here changes a call.
import { useState } from "react";
import type { Pane } from "../../areas";
import { useWords } from "../../words";
import { money } from "../_kit/data";
import { useCountUp } from "../_kit/hooks";
import { BUDGET, MONEY_LEFT, TARGET } from "../_kit/plan";
import { Toast } from "../_kit/Toast";
import { Group, GroupNav, Tile } from "../_kit/ui";
import { watch } from "../_kit/watch";

function MoneyGroup() {
  const t = useWords();
  const [budget, setBudget] = useState(BUDGET);
  const left = useCountUp(MONEY_LEFT);
  const spent = Math.max(0, budget - MONEY_LEFT);
  return (
    <div className="k-grid c2">
      <Tile title={t("v2.tLeft")}>
        <p className="k-big num">{money(Math.round(left), 0)}</p>
        <span className="k-bar-h gain" aria-hidden="true">
          <i
            className="k-grow"
            style={{ width: `${Math.min(100, (MONEY_LEFT / (budget || 1)) * 100)}%` }}
          />
        </span>
        <p className="k-note">
          {t("v3.moneyP")}{" "}
          {t("v3.spentOf").replace("{a}", money(spent, 0)).replace("{b}", money(budget, 0))}
        </p>
      </Tile>
      <Tile title={t("v2.setBudget")}>
        <p className="k-note">{t("v2.setBudgetP")}</p>
        <div className="k-bar">
          <input
            className="k-input"
            type="number"
            step={1000}
            value={budget}
            aria-label={t("v2.setBudget")}
            onChange={(e) => setBudget(Number(e.target.value))}
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
    </div>
  );
}

function MixGroup() {
  const t = useWords();
  const [target, setTarget] = useState(TARGET);
  const sum = Object.values(target).reduce((a, b) => a + b, 0);
  return (
    <Tile title={t("v2.pMix")} wide>
      <p className="k-note">{t("v2.setMixP")}</p>
      <div className="st-mix">
        {Object.entries(target).map(([s, g]) => (
          <label key={s} className="st-row">
            <span>{s}</span>
            <input
              type="range"
              min={0}
              max={40}
              value={g}
              aria-label={`${s} ${t("v2.mixTarget")}`}
              onChange={(e) => setTarget({ ...target, [s]: Number(e.target.value) })}
            />
            <b className="num">{g}%</b>
          </label>
        ))}
      </div>
      <div className="k-bar">
        <span className={`k-note num ${sum === 100 ? "up" : "dn"}`}>
          {t("v3.mixSum").replace("{n}", String(sum))}
        </span>
        <button
          type="button"
          className="sk-btn sk-tonal"
          disabled={sum !== 100}
          onClick={() => watch.say(t("v2.approvedT"))}
        >
          {t("v2.approveT")}
        </button>
        <button type="button" className="sk-btn" onClick={() => setTarget(TARGET)}>
          {t("v3.mixReset")}
        </button>
      </div>
      <p className="k-note">{t("v3.ownerOnly")}</p>
    </Tile>
  );
}

function SettingsScreen() {
  const t = useWords();
  return (
    <section className="st">
      <header className="k-head">
        <p className="k-eyebrow">{t("shell.nav.settings")}</p>
        <h1>{t("v3.settingsH")}</h1>
        <p>{t("v3.settingsP")}</p>
      </header>
      <GroupNav
        label={t("v3.groupsNav")}
        items={[
          { id: "money", label: t("v3.stMoney") },
          { id: "mix", label: t("v2.pMix") },
        ]}
      />
      <Group id="money" title={t("v3.stMoney")} sub={t("v3.stMoneyP")}>
        <MoneyGroup />
      </Group>
      <Group id="mix" title={t("v2.pMix")} sub={t("v3.stMixP")}>
        <MixGroup />
      </Group>
      <Toast />
      <p className="k-sample">{t("v2.proto")}</p>
    </section>
  );
}
const pane: Pane = {
  id: "settings",
  path: "/settings",
  titleKey: "shell.nav.settings",
  Component: SettingsScreen,
};
export default pane;
