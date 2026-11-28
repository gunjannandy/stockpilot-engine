// Analyse on the call card: one button, a progress bar that knows the usual time, English and Bengali from one answer.
import { useEffect, useRef, useState } from "react";
import { useWords } from "../../words";

const USUAL_MIN = 4;
const DEMO_MS = 7000; // the prototype plays the usual four minutes in seven seconds

export function Analyse({ what }: { what: string }) {
  const t = useWords();
  const [p, setP] = useState<number | null>(null);
  const [done, setDone] = useState(false);
  const raf = useRef(0);
  useEffect(() => () => cancelAnimationFrame(raf.current), []);
  const start = () => {
    setDone(false);
    const t0 = performance.now();
    const step = (now: number) => {
      const x = Math.min(1, (now - t0) / DEMO_MS);
      setP(x);
      if (x < 1) raf.current = requestAnimationFrame(step);
      else {
        setDone(true);
        setP(null);
      }
    };
    raf.current = requestAnimationFrame(step);
  };
  const left = p === null ? 0 : Math.max(1, Math.ceil(USUAL_MIN * (1 - p)));
  return (
    <div className="k-analyse">
      <div className="k-bar">
        <button type="button" className="sk-btn sk-tonal" disabled={p !== null} onClick={start}>
          {p !== null ? t("v3.analysing") : done ? t("v3.analyseAgain") : t("v2.ask")}
        </button>
        {done && <span className="k-pill better k-in">{t("v3.analysedNow")}</span>}
      </div>
      {p !== null && (
        <>
          <span
            className="k-bar-h"
            role="progressbar"
            aria-valuenow={Math.round(p * 100)}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`${t("v3.analysing")} ${what}`}
          >
            <i style={{ width: `${p * 100}%`, transition: "none" }} />
          </span>
          <p className="k-note">
            {t("v3.analyseLeft").replace("{m}", String(left)).replace("{u}", String(USUAL_MIN))}
          </p>
        </>
      )}
      <p className="k-note">{t("v3.analyseNote")}</p>
    </div>
  );
}
