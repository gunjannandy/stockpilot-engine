"""What `sp verify` leaves behind: a status file, a one-line summary, gap rows for Health, and one GitHub issue per failed check."""
import json
from datetime import date
from pathlib import Path

from stockpilot import gaps as gaps_mod
from stockpilot.verify import PASS, Result

LABEL = "verify"
GAP_TAG = "verify: "          # every gap this lane records starts its detail with this, so a later run can close them
MAX_LINES = 40


def counts(results: list[Result]) -> dict:
    return {"checks": len(results), "passed": sum(r.status == PASS for r in results),
            "hard_failed": [r.id for r in results if r.blocks],
            "soft_failed": [r.id for r in results if r.status != PASS and not r.hard]}


def summary_line(results: list[Result], day: date, path: Path | None = None) -> str:
    c = counts(results)
    hard = f"{len(c['hard_failed'])} hard fail ({', '.join(map(str, c['hard_failed']))})" if c["hard_failed"] else "no hard fail"
    soft = f", {len(c['soft_failed'])} soft fail ({', '.join(map(str, c['soft_failed']))})" if c["soft_failed"] else ""
    line = f"verify {day}: {c['passed']} of {c['checks']} checks pass, {hard}{soft}."
    return line + (f" Report: {path}" if path else "")


def payload(results: list[Result], day: date) -> dict:
    return {"day": str(day), **counts(results), "ok": not counts(results)["hard_failed"],
            "results": [{"id": r.id, "name": r.name, "hard": r.hard, "status": r.status, "summary": r.summary, "numbers": r.numbers,
                         "problems": r.problems, "notes": r.notes, "gaps": [g.__dict__ for g in r.gaps]} for r in results]}


def markdown(results: list[Result], day: date, issues: list | None = None, notes: list[str] | None = None) -> str:
    lines = [f"# Verify {day}", "", summary_line(results, day), ""]
    lines += notes or []
    lines += ["", "| # | Check | Kind | Result |", "|---|---|---|---|"]
    lines += [f"| {r.id} | {r.name} | {'hard' if r.hard else 'soft'} | {r.label} |" for r in results]
    for r in results:
        lines += ["", f"## {r.id}. {r.name} ({'hard' if r.hard else 'soft'}): {r.label}", "", r.summary or ""]
        if r.numbers:
            lines += ["", "Numbers: `" + json.dumps(r.numbers, default=str, sort_keys=True)[:600] + "`"]
        if r.notes:
            lines += [""] + [f"- Note: {n}" for n in r.notes[:MAX_LINES]]
        if r.problems:
            lines += [""] + [f"- {p}" for p in r.problems[:MAX_LINES]]
            if len(r.problems) > MAX_LINES:
                lines.append(f"- ... and {len(r.problems) - MAX_LINES} more")
    if issues:
        lines += ["", "## Issues", ""] + [f"- {title}: {url}" for title, url in issues]
    return "\n".join(lines) + "\n"


def write(results: list[Result], day: date, folder: Path, issues=None, notes=None) -> Path:
    path = Path(folder) / f"verify-{day}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown(results, day, issues, notes))
    return path


def record_gaps(db, results: list[Result]) -> tuple[int, int]:
    """Record every gap the checks found; close the ones from an earlier verify run that no longer hold. Returns (recorded, closed)."""
    seen = set()
    for r in results:
        for g in r.gaps:
            gaps_mod.record(db, g.area, g.subject, g.reason, GAP_TAG + g.detail)
            seen.add((g.area, g.subject))
    closed = 0
    for area, subject, detail in db.execute("select area, subject, detail from gaps where resolved_at is null").fetchall():
        if (detail or "").startswith(GAP_TAG) and (area, subject) not in seen:
            gaps_mod.resolve(db, area, subject)
            closed += 1
    return len(seen), closed


def _title(r: Result) -> str:
    return f"[{LABEL}] check {r.id}: {r.name}"


def _body(r: Result, day: date) -> str:
    problems = "\n".join(f"- {p}" for p in r.problems[:30]) + (f"\n- ... and {len(r.problems) - 30} more" if len(r.problems) > 30 else "")
    return (f"{'Hard' if r.hard else 'Soft'} failure of verify check {r.id} on {day}.\n\n{r.summary}\n\n{problems}\n\n"
            f"Numbers: `{json.dumps(r.numbers, default=str, sort_keys=True)[:500]}`\n\n"
            f"Run `uv run sp verify --site <folder>` to see it again; the full report is `docs/status/verify-{day}.md`. "
            f"{'A hard failure blocks the deploy.' if r.hard else 'A soft failure does not block the deploy.'}")


def open_issues(results: list[Result], day: date, gh) -> list[tuple[str, str]]:
    """One issue per failed check, never a second one with the same title while it is open. `gh(*args) -> stdout` is injected."""
    failed = [r for r in results if r.status != PASS]
    if not failed:
        return []
    try:
        gh("label", "create", LABEL, "--color", "D93F0B", "--description", "Found by sp verify")
    except Exception:       # noqa: BLE001 - the label exists already
        pass
    try:
        open_titles = {i["title"]: i["number"] for i in json.loads(gh("issue", "list", "--label", LABEL, "--state", "open",
                                                                         "--json", "number,title", "--limit", "100") or "[]")}
    except Exception:       # noqa: BLE001 - cannot read issues: do not guess, do not open duplicates blindly
        return [(_title(r), "not opened: could not list open issues") for r in failed]
    out = []
    for r in failed:
        title = _title(r)
        if title in open_titles:
            out.append((title, f"already open (#{open_titles[title]})"))
            continue
        try:
            out.append((title, gh("issue", "create", "--label", LABEL, "--title", title, "--body", _body(r, day)).strip()))
        except Exception as err:    # noqa: BLE001
            out.append((title, f"not opened: {str(err)[:120]}"))
    return out
