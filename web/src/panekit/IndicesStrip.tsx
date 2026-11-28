// The data pattern on its smallest pane: one typed route, the freshness chip, and the four states.
// Market and news mounts this (or replaces it); it is also the copy-from example in panes/README.md.
import { type IndicesResponse, screenRoutes } from "@stockpilot/contract";
import { pct } from "../format";
import { useWords } from "../words";
import { Pane } from "./Pane";

export function IndicesStrip() {
  const t = useWords();
  return (
    <Pane<IndicesResponse>
      id="indices"
      title={t("panes.indices.title")}
      route={screenRoutes.indices}
      updatedAt={(d) => d.as_of}
      windowHours={30}
      isEmpty={(d) => d.indices.length === 0}
    >
      {(d) => (
        <ul className="indices">
          {d.indices.map((i) => (
            <li key={i.id}>
              <b>{i.name}</b>{" "}
              {i.close === null ? t("panes.indices.none") : i.close.toLocaleString("en-IN")}{" "}
              {i.change_pct === null ? null : <span>{pct(i.change_pct, 2)}</span>}
            </li>
          ))}
        </ul>
      )}
    </Pane>
  );
}
