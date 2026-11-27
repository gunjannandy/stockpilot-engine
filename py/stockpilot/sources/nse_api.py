"""The NSE website JSON API: undocumented, Akamai-fronted, and grey under NSE's terms. Use it only for
what no static archive file has (holidays, ASM/GSM lists, corporate actions, announcements), at most a
few calls a day, through one cookie session, under one request a second."""
import http.cookiejar
import json
import time
import urllib.error
import urllib.request

HOST = "https://www.nseindia.in"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": HOST + "/",
}


class Session:
    """fetch_json(path) -> parsed JSON. Primes cookies from the home page first (that page may 403; the
    cookies still arrive), then spaces requests at least a second apart."""

    def __init__(self):
        jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        self._primed = False
        self._last = 0.0

    def _get(self, url):
        wait = 1.1 - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()
        return self._opener.open(urllib.request.Request(url, headers=HEADERS), timeout=30).read()

    def _prime(self):
        try:
            self._get(HOST + "/")
        except urllib.error.HTTPError:
            pass
        self._primed = True

    def fetch_json(self, path: str):
        """Up to three tries. A timeout, a connection error, an HTTP error or a reply that is not JSON each cost a try;
        the cookies are primed again before the next one (a stale session is the usual cause)."""
        for attempt in range(3):
            try:
                if not self._primed:
                    self._prime()
                return json.loads(self._get(HOST + path))
            except (OSError, json.JSONDecodeError):      # URLError, HTTPError and timeouts are all OSError
                if attempt == 2:
                    raise
                self._primed = False
                time.sleep(2 ** attempt)
        return None
