"""C-140-1: the privacy check catches planted fixtures in a diff, title and body."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from gates import privacy  # noqa: E402

# Planted values are built at run time so this file passes its own scan.
PAN = "QWERT" + "9876Z"
ISIN = "INE" + "009A01021"
RUPEES = "Rs. 12," + "50,000"
EMAIL = "someone" + "@example.org"
NAME = "Zorro " + "Quimby"
DENY = [NAME]


def rules(text):
    return {f.rule for f in privacy.scan_text("diff", text, DENY)}


def test_each_planted_fixture_is_caught_in_a_diff():
    diff = "\n".join([
        "diff --git a/x.py b/x.py", "+++ b/x.py", "@@ -0,0 +1,5 @@",
        f"+pan = '{PAN}'", f"+isin = '{ISIN}'", f"+paid = '{RUPEES}'", f"+mail = '{EMAIL}'", f"+who = '{NAME.lower()}'",
    ])
    assert {"pan", "isin", "rupee-amount", "email", "deny-term"} <= {f.rule for f in privacy.scan_diff(diff, DENY)}


def test_title_and_body_are_scanned_too():
    found = privacy.scan_pr(title=f"fix for {NAME}", body=f"holding {ISIN} for {RUPEES}", diff="", deny_terms=DENY)
    assert {(f.where, f.rule) for f in found} >= {("title", "deny-term"), ("body", "isin"), ("body", "rupee-amount")}


def test_only_added_lines_count_and_clean_text_passes():
    diff = f"--- a/x\n+++ b/x\n-old = '{PAN}'\n+new = 1\n"
    assert privacy.scan_diff(diff, DENY) == []
    assert rules("a plain sentence about the page") == set()


def test_placeholders_are_not_findings():
    assert rules("pan ABCDE1234F, mail a@example.com, noreply@github.com") == set()


def test_a_finding_never_carries_the_matched_text():
    for f in privacy.scan_pr(title=NAME, body=f"{PAN} {ISIN}", diff="", deny_terms=DENY):
        assert PAN not in repr(f) and NAME not in repr(f) and ISIN not in repr(f)


def test_a_missing_deny_list_blocks():
    import pytest
    with pytest.raises(privacy.NoDenyList):
        privacy.load_deny_terms(None)
    assert privacy.load_deny_terms("# note\nalpha\n\nbeta\n") == ["alpha", "beta"]
