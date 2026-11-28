import { useWords } from "../../words";
import { useWatch, watch } from "./watch";

/** The one place an "Undo" shows for eight seconds after a star, hide or never-show. */
export function Toast() {
  const t = useWords();
  const { toast } = useWatch();
  if (!toast) return null;
  return (
    <output className="k-toast">
      <span>{toast.text}</span>
      <button
        type="button"
        onClick={() => {
          toast.undo();
          watch.clearToast();
        }}
      >
        {t("v2.undo")}
      </button>
    </output>
  );
}
