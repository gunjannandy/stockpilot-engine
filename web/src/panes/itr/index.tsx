import { useState } from "react";
import type { Pane } from "../../areas";
import { useWords } from "../../words";

/** The tax year now running: starts 1 April (IST day text is not needed to pick a default). */
export function currentFy(now: Date = new Date()): number {
  return now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1;
}

export function ItrPane() {
  const t = useWords();
  const last = currentFy() - 1;
  const years = [last + 1, last, last - 1, last - 2];
  const [fy, setFy] = useState(last);
  const label = (y: number) => `${y}-${String((y + 1) % 100).padStart(2, "0")}`;
  return (
    <section>
      <h1>{t("itr.title")}</h1>
      <p>{t("itr.about")}</p>
      <p>
        <label>
          {t("itr.year")}{" "}
          <select value={fy} onChange={(e) => setFy(Number(e.target.value))} data-testid="itr-year">
            {years.map((y) => (
              <option key={y} value={y}>
                {label(y)}
              </option>
            ))}
          </select>
        </label>
      </p>
      <p>
        <a className="button" href={`/api/itr/pack?fy=${fy}`} download data-testid="itr-download">
          {t("itr.download")}
        </a>
      </p>
      <p>{t("itr.check")}</p>
    </section>
  );
}

const pane: Pane = { id: "itr", path: "/itr", titleKey: "itr.title", Component: ItrPane };
export default pane;
