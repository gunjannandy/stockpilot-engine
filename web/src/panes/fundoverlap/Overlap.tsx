// A fund's overlap with the stocks we hold, from the fund houses' monthly holdings. Made-up weights.
import { useWords } from "../../words";
import { HOLDINGS } from "../_kit/data";
import { Sec } from "../_kit/ui";

export function Overlap({ name }: { name: string }) {
  const t = useWords();
  const h = [...name].reduce((a, c) => a + c.charCodeAt(0), 0);
  if (h % 5 === 0) {
    return (
      <Sec icon="peers" title={t("v2.fxOvT")} sub={t("v2.fxOvNone")}>
        <p className="k-note">{t("v2.fxOvNone")}</p>
      </Sec>
    );
  }
  const shared = HOLDINGS.filter((r) => (h + r.st.seed) % 3 !== 0).map((r) => ({
    name: r.st.name,
    w: 1 + ((h + r.st.seed * 7) % 60) / 10,
  }));
  const total = shared.reduce((a, s) => a + s.w, 0);
  return (
    <Sec icon="peers" title={t("v2.fxOvT")} sub={t("v2.fxOvP")}>
      {shared.length === 0 ? (
        <p>{t("v2.fxOvZero")}</p>
      ) : (
        <>
          <p className="k-big num">
            {total.toFixed(1)}% <span className="k-note">{t("v2.fxOvOf")}</span>
          </p>
          <span className={`k-bar-h ${total > 25 ? "loss" : ""}`} aria-hidden="true">
            <i style={{ width: `${Math.min(100, total * 2.5)}%` }} />
          </span>
          <ul className="k-ul k-ovl">
            {shared.map((s) => (
              <li key={s.name}>
                {s.name} <b className="num">{s.w.toFixed(1)}%</b>
              </li>
            ))}
          </ul>
          {total > 25 && <p className="k-note">{t("v3.ovHigh")}</p>}
        </>
      )}
    </Sec>
  );
}
