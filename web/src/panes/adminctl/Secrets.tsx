// The secrets tracker: each key, where it runs out, and a warning 30 days ahead. Names and dates are made up.
import { useWords } from "../../words";
import { Tile } from "../_kit/ui";

const ROWS: { name: string; days: number | null | "never"; emailed?: boolean }[] = [
  { name: "Cloudflare deploy key", days: 212 },
  { name: "Bot app key", days: 340 },
  { name: "Broker API secret", days: 9, emailed: true },
  { name: "Claude setup token", days: 22 },
  { name: "Sign-in secret, production", days: "never" },
  { name: "Apps Script key", days: null },
];

export function Secrets() {
  const t = useWords();
  return (
    <Tile title={t("secrets.title")} wide>
      <p className="k-note">{t("secrets.intro")}</p>
      <div className="k-scroll">
        <table className="k-table">
          <thead>
            <tr>
              <th>{t("secrets.name")}</th>
              <th>{t("secrets.left")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {ROWS.map((r) => {
              const due = typeof r.days === "number" && r.days <= 30;
              return (
                <tr key={r.name}>
                  <td>{r.name}</td>
                  <td>
                    {r.days === "never" ? (
                      t("secrets.never")
                    ) : r.days === null ? (
                      t("secrets.unknown")
                    ) : (
                      <span className="k-sec-days">
                        <span className={`k-bar-h ${due ? "loss" : "gain"}`} aria-hidden="true">
                          <i style={{ width: `${Math.min(100, (r.days / 365) * 100)}%` }} />
                        </span>
                        <b className="num">{r.days}</b>
                      </span>
                    )}
                  </td>
                  <td>
                    {r.days !== null && (
                      <span className={`k-pill ${due ? "worse" : "better"}`}>
                        {due ? t("secrets.due") : t("secrets.ok")}
                      </span>
                    )}
                    {r.emailed && <span className="k-note"> {t("secrets.emailed")}</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Tile>
  );
}
