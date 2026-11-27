"""Privacy gate: a PR's diff (added lines), title and body must carry no name, rupee amount, PAN or ISIN.

A finding names where, which line and which rule. It never holds the matched text, so logs stay clean.
The deny list of names arrives as one CI secret (PRIVACY_DENY_LIST), one term per line.
"""
import re
from dataclasses import dataclass

PAN = re.compile(r"(?<![A-Za-z0-9])[A-Z]{5}[0-9]{4}[A-Z](?![A-Za-z0-9])")
DUMMY_PAN = re.compile(r"^(ABCDE1234F|([A-Z])\2{4}(\d)\3{3}\2)$")  # obvious placeholders
ISIN = re.compile(r"(?<![A-Za-z0-9])IN[EF][0-9A-Z]{8}[0-9](?![A-Za-z0-9])")
RUPEES = re.compile(r"(?:₹|\bRs\.?|\bINR)\s?\d[\d,]*(?:\.\d+)?", re.I)
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})")
SAFE_EMAIL = re.compile(r"^(noreply|no-reply)@|@(example\.com|[\w.-]*\.test|users\.noreply\.github\.com|anthropic\.com|google\.com)$", re.I)
ACCOUNT = re.compile(r"(?<![\w.\-])\d{9,18}(?![\w.\-])")
ACCOUNT_CONTEXT = re.compile(r"\baccounts?\b|\ba/c\b|\bacct\b|\bfolio\b|client[ _-]?id|\bdemat\b|\bdp[ _-]?id|\bifsc\b|\biban\b|\bbo[ _-]?id\b", re.I)


class NoDenyList(Exception):
    """Without the list the check cannot vouch for anything, so it blocks."""


@dataclass(frozen=True)
class Finding:
    where: str  # "title", "body" or a diff file path
    line: int
    rule: str

    def __str__(self):
        return f"{self.where}:{self.line}: {self.rule}"


def load_deny_terms(text):
    if not text or not text.strip():
        raise NoDenyList("PRIVACY_DENY_LIST is empty or missing: the privacy check cannot run")
    terms = [ln.strip() for ln in text.splitlines()]
    return [t for t in terms if t and not t.startswith("#")]


def scan_text(where, text, deny_terms, first_line=1):
    terms = [t.lower() for t in deny_terms]
    found = []
    for n, line in enumerate(text.splitlines(), first_line):
        low = line.lower()
        if any(not DUMMY_PAN.match(m.group(0)) for m in PAN.finditer(line)):
            found.append(Finding(where, n, "pan"))
        if ISIN.search(line):
            found.append(Finding(where, n, "isin"))
        if RUPEES.search(line):
            found.append(Finding(where, n, "rupee-amount"))
        if any(not SAFE_EMAIL.search(m.group(0)) for m in EMAIL.finditer(line)):
            found.append(Finding(where, n, "email"))
        if ACCOUNT.search(line) and ACCOUNT_CONTEXT.search(line):
            found.append(Finding(where, n, "account-number"))
        if any(t in low for t in terms):
            found.append(Finding(where, n, "deny-term"))
    return found


_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)")


def scan_diff(diff, deny_terms):
    """Scan the lines a unified diff adds, reporting the new file's path and line number."""
    found, path, n = [], "?", 0
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            path = raw[4:].removeprefix("b/")
        elif raw.startswith("--- ") or raw.startswith("diff "):
            continue
        elif m := _HUNK.match(raw):
            n = int(m.group(1))
        elif raw.startswith("+"):
            found += scan_text(path, raw[1:], deny_terms, first_line=n)
            n += 1
        elif not raw.startswith("-"):
            n += 1
    return found


def scan_pr(title, body, diff, deny_terms):
    return scan_text("title", title or "", deny_terms) + scan_text("body", body or "", deny_terms) + scan_diff(diff or "", deny_terms)
