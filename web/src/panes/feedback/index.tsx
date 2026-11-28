import "./feedback.css";
import { type FeedbackAsk, FeedbackList } from "@stockpilot/contract";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { Pane } from "../../areas";
import { useWords } from "../../words";

async function send<T>(path: string, method: "GET" | "POST", body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as T;
}

const TONE: Record<FeedbackAsk["status"], string> = {
  received: "v-keep",
  reviewed: "v-keep",
  planned: "v-keep",
  being_built: "v-weak",
  done: "v-buy",
  not_planned: "v-sell",
};

function Review({ ask }: { ask: FeedbackAsk }) {
  const t = useWords();
  const qc = useQueryClient();
  const [understanding, setUnderstanding] = useState(ask.understanding ?? "");
  const [decision, setDecision] = useState<"reviewed" | "not_planned">("reviewed");
  const save = useMutation({
    mutationFn: () => send(`/api/feedback/${ask.id}/review`, "POST", { understanding, decision }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["feedback"] }),
  });
  return (
    <details className="fb-review">
      <summary>{t("feedback.review")}</summary>
      <label>
        {t("feedback.understanding")}
        <textarea
          value={understanding}
          onChange={(e) => setUnderstanding(e.target.value)}
          rows={2}
        />
      </label>
      <label>
        {t("feedback.setTo")}
        <select value={decision} onChange={(e) => setDecision(e.target.value as typeof decision)}>
          <option value="reviewed">{t("feedback.status.reviewed")}</option>
          <option value="not_planned">{t("feedback.status.not_planned")}</option>
        </select>
      </label>
      <button
        type="button"
        disabled={!understanding.trim() || save.isPending}
        onClick={() => save.mutate()}
      >
        {t("feedback.save")}
      </button>
      {save.isError && <p role="alert">{t("feedback.failed")}</p>}
    </details>
  );
}

export function FeedbackPane() {
  const t = useWords();
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const list = useQuery({
    queryKey: ["feedback"],
    queryFn: async () => FeedbackList.parse(await send("/api/feedback", "GET")),
    refetchInterval: 30_000,
  });
  const post = useMutation({
    mutationFn: (value: string) => send("/api/feedback", "POST", { text: value }),
    onSuccess: () => {
      setText("");
      return qc.invalidateQueries({ queryKey: ["feedback"] });
    },
  });
  const owner = list.data?.person === "owner";
  return (
    <section className="pane fb" data-pane="feedback">
      <h1>{t("feedback.title")}</h1>
      <p className="note">{t("feedback.intro")}</p>
      <form
        className="card fb-box"
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim()) post.mutate(text.trim());
        }}
      >
        <label htmlFor="fb-text">{t("feedback.prompt")}</label>
        <textarea id="fb-text" rows={3} value={text} onChange={(e) => setText(e.target.value)} />
        <button type="submit" disabled={!text.trim() || post.isPending}>
          {post.isPending ? t("feedback.sending") : t("feedback.send")}
        </button>
        {post.isSuccess && <output data-testid="received">{t("feedback.status.received")}</output>}
        {post.isError && <p role="alert">{t("feedback.notSent")}</p>}
      </form>
      <h2>{t("feedback.asked")}</h2>
      {list.isError && <p role="alert">{t("feedback.failed")}</p>}
      {list.data && list.data.asks.length === 0 && <p>{t("feedback.none")}</p>}
      <ul className="fb-list">
        {list.data?.asks.map((a) => (
          <li key={a.id} className="card fb-ask" data-status={a.status}>
            <p className="fb-said">{a.text}</p>
            {a.understanding && (
              <p className="note">
                {t("feedback.understood")}: {a.understanding}
              </p>
            )}
            <p>
              <span className={`badge ${TONE[a.status]}`} data-testid="status">
                {t(`feedback.status.${a.status}`)}
              </span>{" "}
              <span className="note" data-testid="job">
                {t("feedback.job")}: {a.job ? `#${a.job}` : t("feedback.noJob")}
              </span>
            </p>
            {owner && a.status === "received" && <Review ask={a} />}
          </li>
        ))}
      </ul>
    </section>
  );
}

const pane: Pane = {
  id: "feedback",
  path: "/feedback",
  titleKey: "feedback.title",
  Component: FeedbackPane,
};
export default pane;
