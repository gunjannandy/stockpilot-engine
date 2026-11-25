"""The `reasoning` objects on a built site, for checks 6, 7 and 10 (lane F1 wrote the functions; this reads the files)."""
import json
from pathlib import Path

from stockpilot import reasoning

TABS = ("today", "calls", "watchlist", "ideas", "portfolio")


def _walk(x):
    if isinstance(x, dict):
        if isinstance(x.get("reasoning"), dict):
            yield x.get("symbol"), x["reasoning"]
        for v in x.values():
            yield from _walk(v)
    elif isinstance(x, list):
        for v in x:
            yield from _walk(v)


def objects(site):
    """(label, symbol, reasoning object) for every object in the tab files and the stock files."""
    data = Path(site) / "data"
    for name in TABS:
        p = data / f"{name}.json"
        if p.exists():
            for symbol, r in _walk(json.loads(p.read_text())):
                yield f"{name}.json {symbol or ''}".strip(), symbol, r
    for p in sorted((data / "stock").glob("*.json")) if (data / "stock").is_dir() else []:
        r = json.loads(p.read_text()).get("reasoning")
        if isinstance(r, dict):
            yield f"stock/{p.name}", p.stem, r


def contract_problems(site) -> tuple[list[str], int]:
    problems, n = [], 0
    for label, _, r in objects(site):
        n += 1
        problems += [f"{label}: reasoning: {e}" for e in reasoning.contract_errors(r)]
    return problems, n


def evidence_problems(site) -> list[str]:
    """A chance on fewer than 30 cases (none counts) must carry evidence_note "limited evidence"; on 0 cases it must say so too."""
    out = []
    for label, _, r in objects(site):
        c = r.get("chance")
        if not c:
            continue
        n = c.get("n")
        if (n is None or n < reasoning.THIN_N) and r.get("evidence_note") != "limited evidence":
            out.append(f"{label}: its base rate rests on {n or 0} cases, but the object does not say \"limited evidence\"")
    return out


def analyst_sentences(r: dict) -> dict:
    """The model-written sentences of one object: analyst for/against lines, the headline when a call exists, the chance explanation."""
    keep = {side: [i for i in r.get(side) or [] if i.get("by") == "analyst"] for side in ("for", "against")}
    if r.get("stance") != "none":
        keep["headline"] = r.get("headline")
    keep["chance"] = {"explain": (r.get("chance") or {}).get("explain")}
    return keep


def trace_problems(site, brief_for=None) -> tuple[list[str], int]:
    """Numbers in an analyst's sentences that are in neither the stock file's own data, the object's chance, levels and track,
    nor (when kept) the day's brief for that stock. Checked on stock files: the other tabs carry the same object."""
    problems, sentences = [], 0
    for p in sorted((Path(site) / "data" / "stock").glob("*.json")):
        doc = json.loads(p.read_text())
        r = doc.get("reasoning")
        if not isinstance(r, dict):
            continue
        parts = analyst_sentences(r)
        sentences += len(parts["for"]) + len(parts["against"]) + bool(parts.get("headline")) + bool((parts["chance"] or {}).get("explain"))
        chance = {k: v for k, v in (r.get("chance") or {}).items() if k != "explain"}      # not the sentence being checked
        pool = reasoning.number_pool({k: v for k, v in doc.items() if k != "reasoning"}, r.get("levels"), chance, r.get("track"),
                                     brief_for(p.stem) if brief_for else None)
        # An analyst line is checked against the data and the brief only, never against itself. The headline and the chance
        # explanation may also quote the lines they summarise (and their weights), so those are added for them alone.
        bad = reasoning.untraced({"for": parts["for"], "against": parts["against"]}, pool)
        lines = [{"w": i.get("weight"), "t": i.get("text")} for i in parts["for"] + parts["against"]]
        bad += [n for n in reasoning.untraced({"headline": parts.get("headline"), "chance": parts["chance"]}, pool | reasoning.number_pool(lines))
                if n not in bad]
        if bad:
            problems.append(f"stock/{p.name}: the analyst wrote {', '.join(bad)}, which are not in its data")
    return problems, sentences
