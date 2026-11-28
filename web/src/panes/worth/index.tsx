// Worth following: one list (Top 10, Just missed, has our view, you hold, falling, busy today) and the Table screener over every stock.
import type { Pane } from "../../areas";
import { useWords } from "../../words";
import { isHeld, type Reason, reasonsOf, STOCKS, UNIVERSE } from "../_kit/data";
import { Find } from "../_kit/Find";
import { ListPage } from "../_kit/ListPage";

// Needs data: the real count of stocks analysed and the count that passed the filters; these two are placeholders.
const UNIVERSE_N = 4832;
const PASSED_N = 218;
const fill = (s: string, v: Record<string, string | number>) =>
  s.replace(/\{(\w+)\}/g, (_, k) => String(v[k] ?? ""));

function Worth() {
  const t = useWords();
  const scope = "follow" as "follow" | "all";
  const base =
    scope === "all" ? UNIVERSE : STOCKS.filter((s) => !isHeld(s) || s.verdict !== "keep");
  const has = (r: Reason) => (s: (typeof STOCKS)[number]) => reasonsOf(s).includes(r);
  const reasonText = (s: (typeof STOCKS)[number]) => reasonsOf(s).map((r) => t(`v3.reason.${r}`));
  return (
    <ListPage
      eyebrow={t(scope === "all" ? "v2.universeS" : "v2.follow")}
      title={scope === "all" ? t("v2.universe") : fill(t("v3.followN"), { n: base.length })}
      sub={scope === "all" ? t("v2.universeP") : t("v2.followP")}
      updated={t("v3.updatedAt")}
      rows={base}
      chips={[
        { id: "all", label: t("v2.all"), test: () => true },
        { id: "top", label: t("v2.fTop"), test: has("top") },
        { id: "near", label: t("v2.fNear"), test: has("near") },
        { id: "view", label: t("v2.fView"), test: has("view") },
        { id: "held", label: t("v2.fHeld"), test: has("held") },
        { id: "fall", label: t("v2.fFall"), test: has("fall") },
        { id: "busy", label: t("v2.fBusy"), test: has("busy") },
      ]}
      groupOf={(s) =>
        s.verdict === "buy"
          ? { id: "close", label: t("v2.gClose"), cls: "r-buy", sentence: t("v2.secNearP") }
          : { id: "watch", label: t("v3.watchOut"), cls: "r-watch", sentence: t("v3.watchOutP") }
      }
      groupOrder={["close", "watch"]}
      reasonsOf={reasonText}
      tableCols={["sector", "pe", "growth"]}
      empty={t("v2.noneHere")}
      top={
        <>
          <div className="wl-glance wt-funnel" aria-label={t("v3.funnelT")}>
            {[
              [UNIVERSE_N.toLocaleString("en-IN"), t("v3.funAnalysed")],
              [PASSED_N.toLocaleString("en-IN"), t("v3.funPassed")],
              [String(base.length), t("v3.funShown")],
            ].map(([n, l], i) => (
              <div key={l} className="wl-g" style={{ animationDelay: `${i * 80}ms` }}>
                <b className="num">{n}</b>
                <span className="k-note">{l}</span>
              </div>
            ))}
          </div>
          <Find placeholder={t("v3.findAny")} />
        </>
      }
    />
  );
}
const pane: Pane = { id: "worth", path: "/worth", titleKey: "shell.nav.worth", Component: Worth };
export default pane;
