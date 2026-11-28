import { useEffect, useRef, useState } from "react";

/** Counts a number up once when it first shows, unless the reader asked for less motion. */
export function useCountUp(target: number, ms = 700) {
  const [v, setV] = useState(target);
  const done = useRef(false);
  useEffect(() => {
    if (done.current || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const t0 = performance.now();
    let raf = 0;
    const step = (t: number) => {
      const p = Math.min(1, (t - t0) / ms);
      setV(target * (1 - (1 - p) ** 3));
      if (p < 1) raf = requestAnimationFrame(step);
      else done.current = true;
    };
    setV(0);
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return v;
}

/** A readable date line for the page heading, in IST. */
export function todayLine(lang: "en" | "bn" = "en") {
  return new Intl.DateTimeFormat(lang === "bn" ? "bn-IN" : "en-IN", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "Asia/Kolkata",
  }).format(new Date("2026-11-28T09:30:00+05:30"));
}
