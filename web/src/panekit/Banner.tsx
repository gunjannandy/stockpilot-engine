// Banner flags: a screen or a section the owner has put "under maintenance" shows only its banner.
// The flags come from GET /api/flags (cached); until they load, or if they cannot load, the release plan's
// defaults in the contract decide (the five live screens open, the rest bannered).
import { isBannered } from "@stockpilot/contract";
import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useWords } from "../words";

export function useFlags(): Record<string, boolean> {
  const q = useQuery({
    queryKey: ["flags"],
    queryFn: async () => {
      const r = await fetch("/api/flags");
      if (!r.ok) throw new Error(`flags ${r.status}`);
      return ((await r.json()) as { flags: Record<string, boolean> }).flags;
    },
    staleTime: 60_000,
    retry: false,
  });
  return q.data ?? {};
}

export function Banner({ id, whole }: { id: string; whole: boolean }) {
  const t = useWords();
  return (
    <section
      className={whole ? "card pane-banner" : "pane-banner section"}
      data-testid={`banner-${id}`}
    >
      {whole ? <h1>{t("panes.banner.title")}</h1> : <h2>{t("panes.banner.title")}</h2>}
      <p>{t("panes.banner.body")}</p>
    </section>
  );
}

/** Wraps a whole screen (the router does this for every pane), or one section of it with `section`. */
export function Bannered({
  screen,
  section,
  children,
}: {
  screen: string;
  section?: string;
  children: ReactNode;
}) {
  const flags = useFlags();
  if (isBannered(flags, screen, section))
    return <Banner id={section ? `${screen}-${section}` : screen} whole={section === undefined} />;
  return <>{children}</>;
}
