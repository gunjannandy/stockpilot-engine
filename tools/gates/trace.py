"""Trace gate: every story in checks/trace.csv has at least one well-formed, unique check."""
import csv
import io
import re

CHECK_ID = re.compile(r"^C-\d{3}-\d+$")


def parse(text):
    return list(csv.DictReader(io.StringIO(text)))


def check_text(text):
    rows, problems, seen = parse(text), [], set()
    if not rows:
        return ["trace.csv has no rows"]
    for n, r in enumerate(rows, 2):
        story, cid = (r.get("story") or "").strip(), (r.get("check_id") or "").strip()
        if not story:
            problems.append(f"line {n}: a check with no story")
        if not cid:
            problems.append(f"line {n}: story {story} has no check")
        elif not CHECK_ID.match(cid):
            problems.append(f"line {n}: check id {cid!r} is not C-nnn-n")
        elif cid in seen:
            problems.append(f"line {n}: duplicate check id {cid}")
        seen.add(cid)
    return problems
