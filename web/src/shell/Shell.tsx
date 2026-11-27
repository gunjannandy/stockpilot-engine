// The frame every screen sits in: rail (icons at 1100, bottom bar at 400), top bar, one page.
// The rail comes from the layout row; the top bar holds search, the sync time, language, theme, text size.
import { Link, Outlet } from "@tanstack/react-router";
import { createContext, useContext, useEffect, useRef, useState } from "react";
import type { Pane } from "../areas";
import {
  getLang,
  getSize,
  getTheme,
  type LangChoice,
  type SizeChoice,
  setLang,
  setSize,
  setTheme,
  type ThemeChoice,
} from "../theme/theme";
import { useWords } from "../words";
import { Icon } from "./icons";
import { fetchLayout, type LayoutRow, railItems } from "./layout";

const Screens = createContext<Pane[]>([]);

function Segmented<T extends string>(props: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onPick: (v: T) => void;
}) {
  return (
    <fieldset className="seg">
      <legend>{props.label}</legend>
      {props.options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={props.value === o.value}
          onClick={() => props.onPick(o.value)}
        >
          {o.label}
        </button>
      ))}
    </fieldset>
  );
}

export function Shell({ panes, syncedAt }: { panes: Pane[]; syncedAt?: string }) {
  const t = useWords();
  const [row, setRow] = useState<LayoutRow | null>(null);
  const [theme, setThemeState] = useState<ThemeChoice>(getTheme);
  const [size, setSizeState] = useState<SizeChoice>(getSize);
  const [lang] = useState<LangChoice>(getLang);
  const search = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let live = true;
    fetchLayout().then((r) => live && setRow(r));
    return () => {
      live = false;
    };
  }, []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (e.key === "/" && el?.tagName !== "INPUT" && el?.tagName !== "TEXTAREA") {
        e.preventDefault();
        search.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const items = railItems(panes, row);
  const bar = items.slice(0, 4);
  const item = (p: Pane) => (
    <Link
      key={p.id}
      to={p.path}
      className="nav"
      title={t(p.titleKey)}
      aria-label={t(p.titleKey)}
      activeProps={{ "aria-current": "page" }}
    >
      <Icon name={p.id} />
      <span>{t(p.titleKey)}</span>
    </Link>
  );
  return (
    <div className="shell">
      <a className="skip" href="#page">
        {t("shell.skip")}
      </a>
      <nav className="rail" aria-label={t("shell.nav.label")}>
        <div className="brand">
          <i aria-hidden="true">s</i>
          <span>{t("shell.brand")}</span>
        </div>
        {items.map(item)}
      </nav>
      <nav className="bar" aria-label={t("shell.nav.label")}>
        {bar.map(item)}
        <Link to="/more" className="nav" activeProps={{ "aria-current": "page" }}>
          <Icon name="more" />
          <span>{t("shell.nav.more")}</span>
        </Link>
      </nav>
      <header className="top">
        <label className="search">
          <span className="sr">{t("shell.search")}</span>
          <input ref={search} type="search" placeholder={t("shell.search.hint")} />
        </label>
        <span className="sync note">
          {syncedAt ? `${t("shell.synced")} ${syncedAt}` : t("shell.synced.none")}
        </span>
        <div className="controls">
          <Segmented
            label={t("shell.lang")}
            value={lang}
            options={[
              { value: "en", label: "EN" },
              { value: "bn", label: "বাং" },
            ]}
            onPick={(l) => {
              setLang(l);
              window.location.reload();
            }}
          />
          <fieldset className="seg">
            <legend>{t("shell.theme")}</legend>
            {(["light", "dark"] as const).map((v) => (
              <button
                key={v}
                type="button"
                className="seg-icon"
                aria-pressed={theme === v}
                aria-label={t(`shell.theme.${v}`)}
                title={t(`shell.theme.${v}`)}
                onClick={() => {
                  setTheme(v);
                  setThemeState(v);
                }}
              >
                <Icon name={v === "light" ? "sun" : "moon"} size={18} />
              </button>
            ))}
          </fieldset>
          <Segmented
            label={t("shell.size")}
            value={size}
            options={[
              { value: "normal", label: "A" },
              { value: "large", label: "A+" },
              { value: "xlarge", label: "A++" },
            ]}
            onPick={(v) => {
              setSize(v);
              setSizeState(v);
            }}
          />
        </div>
      </header>
      <main id="page" className="page" tabIndex={-1}>
        <Screens.Provider value={items}>
          <Outlet />
        </Screens.Provider>
      </main>
    </div>
  );
}

/** Phone only: everything the bottom bar has no room for. */
export function MorePane() {
  const t = useWords();
  const screens = useContext(Screens);
  return (
    <section className="card">
      <h1>{t("shell.more.title")}</h1>
      <ul className="more">
        {screens.map((p) => (
          <li key={p.id}>
            <Link to={p.path} className="nav">
              <Icon name={p.id} />
              <span>{t(p.titleKey)}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
