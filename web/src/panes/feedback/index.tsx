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

const STEPS: FeedbackAsk["status"][] = ["received", "reviewed", "planned", "being_built", "done"];
const MAX = 2000;

/** Where an ask stands: five steps, the reached ones filled. Not planned is its own end, shown plainly. */
function Track({ status }: { status: FeedbackAsk["status"] }) {
  const t = useWords();
  const at = STEPS.indexOf(status);
  if (at < 0) return <p className="fb-np">{t("feedback.status.not_planned")}</p>;
  return (
    <ol className="fb-track" aria-label={t(`feedback.status.${status}`)}>
      {STEPS.map((x, i) => (
        <li key={x} className={i <= at ? "on" : ""} aria-current={i === at ? "step" : undefined}>
          <i />
          <span>{t(`feedback.status.${x}`)}</span>
        </li>
      ))}
    </ol>
  );
}

export function FeedbackPane() {
  const t = useWords();
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [show, setShow] = useState<"all" | "open" | "done">("all");
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
  const asks = list.data?.asks ?? [];
  const closed = (a: FeedbackAsk) => a.status === "done" || a.status === "not_planned";
  const vis = asks.filter((a) => show === "all" || (show === "done") === closed(a));
  return (
    <section className="pane fb" data-pane="feedback">
      <header className="k-head">
        <p className="k-eyebrow">{t("feedback.title")}</p>
        <h1>{t("feedback.headline")}</h1>
        <p>{t("feedback.intro")}</p>
      </header>
      <div className="fb-cols">
        <form
          className="card fb-box"
          onSubmit={(e) => {
            e.preventDefault();
            if (text.trim()) post.mutate(text.trim());
          }}
        >
          <label htmlFor="fb-text">{t("feedback.prompt")}</label>
          <textarea
            id="fb-text"
            rows={5}
            maxLength={MAX}
            value={text}
            placeholder={t("feedback.hint")}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="fb-foot">
            <span className="k-note num">
              {text.length}/{MAX}
            </span>
            <button
              type="submit"
              className="sk-btn sk-tonal"
              disabled={!text.trim() || post.isPending}
            >
              {post.isPending ? t("feedback.sending") : t("feedback.send")}
            </button>
          </div>
          {post.isSuccess && (
            <output className="fb-ok" data-testid="received">
              {t("feedback.status.received")}
            </output>
          )}
          {post.isError && <p role="alert">{t("feedback.notSent")}</p>}
        </form>
        <div className="fb-asks">
          <div className="k-bar">
            <h2>{t("feedback.asked")}</h2>
            <div className="k-chips">
              {(["all", "open", "done"] as const).map((k) => (
                <button
                  key={k}
                  type="button"
                  className="k-chipbtn"
                  aria-pressed={show === k}
                  onClick={() => setShow(k)}
                >
                  {t(`feedback.f.${k}`)}
                  <span className="num">
                    {k === "all"
                      ? asks.length
                      : asks.filter((a) => (k === "done") === closed(a)).length}
                  </span>
                </button>
              ))}
            </div>
          </div>
          {list.isError && <p role="alert">{t("feedback.failed")}</p>}
          {list.isPending && <span className="k-skel" />}
          {list.data && vis.length === 0 && <p className="k-note">{t("feedback.none")}</p>}
          <ul className="fb-list">
            {vis.map((a, i) => (
              <li
                key={a.id}
                className="card fb-ask"
                data-status={a.status}
                style={{ animationDelay: `${Math.min(i, 8) * 50}ms` }}
              >
                <p className="fb-said">{a.text}</p>
                {a.understanding && (
                  <p className="fb-und">
                    <b>{t("feedback.understood")}:</b> {a.understanding}
                  </p>
                )}
                <Track status={a.status} />
                <p className="fb-meta">
                  <span className={`badge ${TONE[a.status]}`} data-testid="status">
                    {t(`feedback.status.${a.status}`)}
                  </span>
                  <span className="k-note" data-testid="job">
                    {t("feedback.job")}: {a.job ? `#${a.job}` : t("feedback.noJob")}
                  </span>
                  <span className="k-note num">{a.created_at.slice(0, 10)}</span>
                </p>
                {owner && a.status === "received" && <Review ask={a} />}
              </li>
            ))}
          </ul>
        </div>
      </div>
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
