/* BROWSERFIX: a browser with a thin language library throws RangeError "Incorrect locale information provided" from
   toLocaleString and friends (seen in CI's Chromium on the Bengali date, "bn-IN-u-nu-latn"). A thrown error would blank the
   screen it was drawing, so each formatter tries the asked-for language, then plain English, then the browser's own default.
   Loaded first, so every screen is covered. */
(function (root) {
  "use strict";
  const FALLBACKS = ["en-IN", "en-US", undefined];
  const isLocaleError = e => e instanceof RangeError || /locale/i.test(String(e && e.message));

  function guard(proto, name) {
    const orig = proto && proto[name];
    if (typeof orig !== "function" || orig.__guarded) return;
    const safe = function (locale, ...rest) {
      try { return orig.call(this, locale, ...rest); }
      catch (e) {
        if (!isLocaleError(e)) throw e;
        for (const l of FALLBACKS) { if (l === locale) continue; try { return orig.call(this, l, ...rest); } catch (e2) { if (!isLocaleError(e2)) throw e2; } }
        throw e;
      }
    };
    safe.__guarded = true;
    Object.defineProperty(proto, name, { value: safe, writable: true, configurable: true });
  }

  function install(g) {
    guard(g.Date.prototype, "toLocaleDateString"); guard(g.Date.prototype, "toLocaleString"); guard(g.Date.prototype, "toLocaleTimeString");
    guard(g.Number.prototype, "toLocaleString"); guard(g.String.prototype, "localeCompare");
    const DTF = g.Intl && g.Intl.DateTimeFormat;
    if (DTF && !DTF.__guarded) {
      const safe = function (locale, opts) {
        for (const l of [locale, ...FALLBACKS]) { try { return new DTF(l, opts); } catch (e) { if (!isLocaleError(e)) throw e; } }
        return new DTF(undefined, opts);
      };
      safe.__guarded = true; safe.prototype = DTF.prototype; safe.supportedLocalesOf = DTF.supportedLocalesOf.bind(DTF);
      g.Intl.DateTimeFormat = safe;
    }
  }
  install(root);
  root.SPLocaleGuard = { install };
})(typeof window !== "undefined" ? window : globalThis);
