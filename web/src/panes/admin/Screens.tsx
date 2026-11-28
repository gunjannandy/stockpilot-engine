// Admin's Screens card: one switch per screen. Off puts the screen "under maintenance" (banner.<id>).
import { bannerKey, isBannered } from "@stockpilot/contract";
import { useMutation } from "@tanstack/react-query";
import { useWords } from "../../words";
import { watch } from "../_kit/watch";

const SCREENS = [
  "today",
  "portfolio",
  "market",
  "watchlist",
  "worth",
  "funds",
  "record",
  "feedback",
  "itr",
] as const;

export function Screens({
  flags,
  again,
}: {
  flags: Record<string, boolean> | undefined;
  again: () => void;
}) {
  const t = useWords();
  const set = useMutation({
    mutationFn: async (v: { key: string; enabled: boolean }) => {
      const r = await fetch("/api/admin/flags", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(v),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
    },
    onSuccess: () => {
      again();
    },
    onError: (e) => watch.say(String((e as Error).message)),
  });
  return (
    <section className="ad-screens" data-testid="admin-screens">
      <h2>{t("admin.screens.title")}</h2>
      <p className="k-note">{t("admin.screens.body")}</p>
      <ul>
        {SCREENS.map((id) => {
          const shown = !isBannered(flags ?? {}, id);
          return (
            <li key={id}>
              <span>{t(`shell.nav.${id}`)}</span>
              <button
                type="button"
                role="switch"
                aria-checked={shown}
                aria-label={t(`shell.nav.${id}`)}
                className="ac-sw"
                disabled={!flags || set.isPending}
                onClick={() => set.mutate({ key: bannerKey(id), enabled: shown })}
              >
                <i />
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
