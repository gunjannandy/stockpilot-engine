// Prototype of the What changed screen: made-up rows, so the marks, the strip and the chips can be judged.
import { useState } from "react";
import type { Pane } from "../../areas";
import { PaneRow } from "../../panekit";
import {
  ChangeMark,
  type MarkItem,
  NewsIcon,
  ReasonChips,
  useTabCount,
  WhatChangedStrip,
} from "../../panekit/marks";
import { useWords } from "../../words";

type Stock = { key: string; name: string; call: string; reasons: string[]; news?: boolean };
const STOCKS: Stock[] = [
  { key: "alpha", name: "Alpha Steel", call: "Sell", reasons: ["held"] },
  { key: "echo", name: "Echo Bank", call: "Buy", reasons: ["buyzone", "watch"] },
  { key: "gamma", name: "Gamma Tech", call: "Buy", reasons: ["watch"] },
  { key: "harbor", name: "Harbor Ports", call: "Keep", reasons: ["held", "news"], news: true },
  { key: "juno", name: "Juno Finance", call: "Keep", reasons: ["results"] },
];
const START: MarkItem[] = [
  { dataset: "calls", key: "alpha", runId: "r2", fields: ["call"], isNew: false, seen: false },
  { dataset: "calls", key: "echo", runId: "r2", fields: ["chance_3m"], isNew: false, seen: false },
  { dataset: "calls", key: "gamma", runId: "r2", fields: [], isNew: true, seen: false },
];

function MarksScreen() {
  const t = useWords();
  const [items, setItems] = useState(START);
  const unseen = items.filter((i) => !i.seen).length;
  useTabCount(unseen);
  const clear = (key?: string) =>
    setItems((xs) =>
      xs.map((i) => (key === undefined || i.key === key ? { ...i, seen: true } : i)),
    );
  const name = (i: MarkItem) => STOCKS.find((s) => s.key === i.key)?.name ?? i.key;
  return (
    <section className="marks-screen">
      <h1>{t("marks.title")}</h1>
      <WhatChangedStrip
        items={items}
        nameOf={name}
        onOpen={(i) => clear(i.key)}
        onMarkAll={() => clear()}
      />
      <ul className="marks-list" style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {STOCKS.map((s) => {
          const marked = items.some((i) => i.key === s.key && !i.seen);
          return (
            <PaneRow
              key={s.key}
              reason={<ReasonChips reasons={s.reasons} />}
              change={marked ? <ChangeMark /> : s.news ? <NewsIcon /> : null}
            >
              <button
                type="button"
                onClick={() => clear(s.key)}
                style={{
                  all: "unset",
                  cursor: "pointer",
                  display: "flex",
                  gap: 12,
                  minHeight: 44,
                  alignItems: "center",
                }}
              >
                <b>{s.name}</b>
                <span className="note">{s.call}</span>
              </button>
            </PaneRow>
          );
        })}
      </ul>
      <p className="note">{t("marks.sample")}</p>
    </section>
  );
}

const pane: Pane = {
  id: "changes",
  path: "/changes",
  titleKey: "marks.title",
  Component: MarksScreen,
};
export default pane;
