// The pane wrapper: its own query and boundary; loading, empty, stale and failed states; the
// freshness chip; the calm updating state. A pane gives a route, a way to read the updated time
// and its rows, and how to draw them.
import { routePath, type ScreenRoute } from "@stockpilot/contract";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useWords } from "../words";
import { Boundary } from "./Boundary";
import { fetchPane, type Held, type PaneFetcher, PaneUpdating } from "./fetchPane";
import { FreshnessChip } from "./parts";

export type PaneProps<T> = {
  id: string;
  title: string;
  /** The pane's one API route, as a path. Give this or `route`. */
  path?: string;
  /** The pane's one route from the contract's `screenRoutes` (typed: the answer is checked against it). */
  route?: ScreenRoute;
  /** Fills `:name` in the route's path, e.g. { symbol }. */
  params?: Record<string, string>;
  /** The dataset's updated time (IST text) in an answer. */
  updatedAt: (data: T) => string | null | undefined;
  /** How long the dataset may go before the chip turns amber. */
  windowHours: number;
  isEmpty?: (data: T) => boolean;
  children: (data: T) => ReactNode;
  fetcher?: PaneFetcher;
};

function Failed({ id, retry }: { id: string; retry: () => void }) {
  const t = useWords();
  return (
    <div role="alert" className="pane-state failed" data-testid={`${id}-failed`}>
      <p>{t("panes.failed")}</p>
      <button type="button" onClick={retry}>
        {t("panes.retry")}
      </button>
    </div>
  );
}

function Inner<T>(p: PaneProps<T>) {
  const t = useWords();
  const qc = useQueryClient();
  const path = p.path ?? (p.route ? routePath(p.route, p.params) : "");
  const q = useQuery({
    queryKey: ["pane", path],
    // The cache keeps the ETag next to the body, so a persisted answer can be revalidated too.
    queryFn: async () => {
      const got = await fetchPane<T>(path, qc.getQueryData<Held<T>>(["pane", path]), p.fetcher);
      return p.route ? { ...got, data: p.route.response.parse(got.data) as T } : got;
    },
    retry: (n, err) => !(err instanceof PaneUpdating) && n < 1,
    retryDelay: 300,
    staleTime: 15_000,
  });
  const title = <h2>{p.title}</h2>;
  if (q.error instanceof PaneUpdating)
    return (
      <section className="pane" data-pane={p.id}>
        {title}
        <p className="pane-state updating" data-testid="updating">
          {t("panes.updating")}
        </p>
      </section>
    );
  if (!q.data) {
    if (q.isError)
      return (
        <section className="pane" data-pane={p.id}>
          {title}
          <Failed id={p.id} retry={() => void q.refetch()} />
        </section>
      );
    return (
      <section className="pane" data-pane={p.id} aria-busy="true">
        {title}
        <p className="pane-state loading" data-testid={`${p.id}-loading`}>
          {t("panes.loading")}
        </p>
      </section>
    );
  }
  const data = q.data.data;
  return (
    <section className="pane" data-pane={p.id}>
      <header className="pane-head">
        {title}
        <FreshnessChip updatedAt={p.updatedAt(data)} windowHours={p.windowHours} />
      </header>
      {q.isError ? (
        <output className="pane-state stale" data-testid={`${p.id}-stale`}>
          {t("panes.stale")}
        </output>
      ) : null}
      {p.isEmpty?.(data) ? (
        <p className="pane-state empty" data-testid={`${p.id}-empty`}>
          {t("panes.empty")}
        </p>
      ) : (
        p.children(data)
      )}
    </section>
  );
}

export function Pane<T>(p: PaneProps<T>) {
  const t = useWords();
  return (
    <Boundary
      pane={p.id}
      fallback={
        <section className="pane" data-pane={p.id}>
          <div role="alert" className="pane-state failed" data-testid={`${p.id}-failed`}>
            <p>{t("panes.failed")}</p>
          </div>
        </section>
      }
    >
      <Inner {...p} />
    </Boundary>
  );
}
