// A short "What's new" note, once per person: shown from /api/whatsnew/unseen, gone after "Got it".
import { useEffect, useState } from "react";
import type { LangChoice } from "../theme/theme";
import { useWords } from "../words";

type Line = { pr: number; en: string; bn: string };

export function WhatsNew({ lang }: { lang: LangChoice }) {
  const t = useWords();
  const [lines, setLines] = useState<Line[]>([]);
  useEffect(() => {
    let live = true;
    fetch("/api/whatsnew/unseen")
      .then((r) => (r.ok ? r.json() : { lines: [] }))
      .then((j: { lines?: Line[] }) => live && setLines(j.lines ?? []))
      .catch(() => {});
    return () => {
      live = false;
    };
  }, []);
  const first = lines[0];
  if (!first) return null;
  const done = () => {
    fetch("/api/whatsnew/seen", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ pr: first.pr }),
    }).catch(() => {});
    setLines((l) => l.slice(1));
  };
  return (
    <section className="card whatsnew" aria-live="polite" data-testid="whatsnew">
      <b>{t("search.new.title")}</b>
      <p>{lang === "bn" ? first.bn : first.en}</p>
      <button type="button" onClick={done}>
        {t("search.new.ok")}
      </button>
    </section>
  );
}
