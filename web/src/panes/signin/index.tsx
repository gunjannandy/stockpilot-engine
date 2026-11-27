import type { Pane } from "../../areas";
import { useWords } from "../../words";

/** A plain form that posts to the Worker's /login: it works before any script has run, and the page
 *  the Worker serves to a signed-out visit says the same words. */
export function SignInPane() {
  const t = useWords();
  return (
    <section>
      <h1>{t("signin.title")}</h1>
      <p>{t("signin.intro")}</p>
      <form method="post" action="/login">
        <input type="hidden" name="next" value="/" />
        <label htmlFor="signin-email">{t("signin.email")}</label>
        <input
          id="signin-email"
          type="email"
          name="email"
          autoComplete="email"
          autoCapitalize="off"
          spellCheck={false}
          maxLength={254}
          required
        />
        <button type="submit">{t("signin.send")}</button>
      </form>
      <form method="post" action="/logout">
        <button type="submit">{t("signin.signout")}</button>
      </form>
    </section>
  );
}

const pane: Pane = {
  id: "signin",
  path: "/signin",
  titleKey: "signin.title",
  Component: SignInPane,
};
export default pane;
