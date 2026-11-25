"""The track record: score each call once its window has ended, say how the model and the base rate alone did, and map a
model probability through that history (calibration). `summary` is the one source for status.json and the Record tab.

A call's outcome is "beat the Nifty 50 by more than the call's hurdle" (round-trip costs plus tax on the gain, set when the
call was made; none on old calls, so a raw beat). The model is judged on what it said (`raw_probability`); `probability` is
what code decided on after calibration. Never shown to the deciding model.
Moves to `calls/record.py` when R7 makes the package."""
import bisect
from datetime import date, timedelta

import duckdb

from stockpilot.analysis import analytics

WINDOWS = (("score_1m", 30, "1m"), ("score_3m", 91, "3m"), ("score_6m", 182, "6m"))
PRICE_SLACK_DAYS = 7           # a price this far from the window edge is "no data", not a result
PROVEN_AFTER = 30              # scored 3-month calls before the model is judged, and before calibration starts
P_FLOOR, P_CEIL = 0.02, 0.98   # a calibrated chance is never certain, whatever a small history says

# The latest call per day and stock, so a rerun counts once. Used by every reader of the record.
LATEST = "(select * from calls qualify row_number() over (partition by made_on, symbol order by id desc) = 1)"
MODEL_P = "coalesce(raw_probability, probability)"


def _hit(column: str) -> str:
    """1.0 for a hit whatever the stored number (a score above zero counts), so old rows and new rows read the same."""
    return f"(case when {column} > 0 then 1.0 else 0.0 end)"


# ---- scoring -----------------------------------------------------------------------------------

def _last_on_or_before(rows, day, slack):
    best = None
    for d, v in rows:
        if d <= day:
            best = (d, v)
    return best[1] if best and (day - best[0]).days <= slack else None


def score(db: duckdb.DuckDBPyConnection, today: date) -> int:
    """Fill score_1m/3m/6m (1.0 = beat the Nifty 50 by more than the call's hurdle, 0.0 = did not) once a window has ended.
    Returns the cells filled."""
    filled = 0
    nifty = db.execute("select date, close from index_levels where name = 'Nifty 50' order by date").fetchall()
    for column, days, _ in WINDOWS:
        due = db.execute(f"select id, symbol, made_on, hurdle from calls where {column} is null and made_on + ? <= ?",
                         [days, today]).fetchall()
        for call_id, symbol, made_on, hurdle in due:
            end = made_on + timedelta(days=days)
            rows = analytics.adjusted_closes(db, symbol, made_on - timedelta(days=PRICE_SLACK_DAYS))
            if not rows:
                rows = analytics.adjusted_closes(db, symbol, made_on - timedelta(days=PRICE_SLACK_DAYS), "BSE")
            s0, s1 = _last_on_or_before(rows, made_on, PRICE_SLACK_DAYS), _last_on_or_before(rows, end, PRICE_SLACK_DAYS)
            n0, n1 = _last_on_or_before(nifty, made_on, PRICE_SLACK_DAYS), _last_on_or_before(nifty, end, PRICE_SLACK_DAYS)
            if not (s0 and s1 and n0 and n1):
                continue
            excess = (s1 / s0 - 1) - (n1 / n0 - 1)
            db.execute(f"update calls set {column} = ? where id = ?", [1.0 if excess > (hurdle or 0.0) else 0.0, call_id])
            filled += 1
    return filled


# ---- the summary -------------------------------------------------------------------------------

def summary(db: duckdb.DuckDBPyConnection) -> dict:
    """Per window: n, hit_rate, brier (the model, on every scored call), base_brier (the base rate alone, on the scored calls
    whose base rate had a sample) and brier_vs_base (the model on those same calls). Then `scored_3m`, `unproven`, and
    `model_added_value`: None until 30 calls have a 3-month result to compare, then whether the model's Brier beat the base
    rate's (lower is better; a tie is no)."""
    out = {}
    for column, _, label in WINDOWS:
        n, hits, brier = db.execute(
            f"select count(*), avg({_hit(column)}), avg(pow({MODEL_P} - {_hit(column)}, 2)) from {LATEST} "
            f"where {column} is not null and probability is not null").fetchone()
        nb, base, same = db.execute(
            f"select count(*), avg(pow(base_rate - {_hit(column)}, 2)), avg(pow({MODEL_P} - {_hit(column)}, 2)) from {LATEST} "
            f"where {column} is not null and probability is not null and base_rate is not null "
            f"and coalesce(base_rate_n, 1) > 0").fetchone()
        out[label] = {"n": n, "hit_rate": hits, "brier": brier, "base_n": nb, "base_brier": base, "brier_vs_base": same}
    three = out["3m"]
    out["scored_3m"] = three["n"]
    out["unproven"] = three["n"] < PROVEN_AFTER
    out["model_added_value"] = (three["brier_vs_base"] < three["base_brier"]) if three["base_n"] >= PROVEN_AFTER else None
    return out


def calibration_table(db: duckdb.DuckDBPyConnection, window: str = "3m") -> list[dict]:
    """What the model said against what happened, in tenths: [{said, happened, n}], for the Record tab."""
    column = {label: col for col, _, label in WINDOWS}[window]
    rows = db.execute(f"select {MODEL_P}, {column} from {LATEST} where {column} is not null and probability is not null").fetchall()
    buckets: dict[int, list] = {}
    for p, o in rows:
        buckets.setdefault(min(9, int(p * 10)), []).append((p, 1 if o > 0 else 0))
    return [{"said": round(sum(p for p, _ in v) / len(v), 3), "happened": round(sum(o for _, o in v) / len(v), 3), "n": len(v)}
            for _, v in sorted(buckets.items())]


# ---- calibration -------------------------------------------------------------------------------

def _isotonic(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Pool-adjacent-violators on (x, outcome) pairs: the non-decreasing step fit, as one (mean x, mean outcome) per block."""
    by_x: dict[float, list[float]] = {}
    for x, y in points:
        by_x.setdefault(x, []).append(y)
    blocks: list[list[float]] = []            # [sum of x*weight, sum of y, weight]
    for x in sorted(by_x):
        ys = by_x[x]
        blocks.append([x * len(ys), sum(ys), len(ys)])
        while len(blocks) > 1 and blocks[-2][1] / blocks[-2][2] > blocks[-1][1] / blocks[-1][2]:
            top = blocks.pop()
            blocks[-1] = [a + b for a, b in zip(blocks[-1], top)]
    return [(bx / w, by / w) for bx, by, w in blocks]


def calibrator(db: duckdb.DuckDBPyConnection):
    """A function p -> p fitted to the scored 3-month history (what the model said against what happened). Identity until
    30 calls are scored. Isotonic, so a higher chance never maps lower; read between the blocks' centres in a straight line,
    held flat past the ends, and kept inside 2% to 98%."""
    rows = db.execute(f"select {MODEL_P}, score_3m from {LATEST} where score_3m is not null and probability is not null").fetchall()
    if len(rows) < PROVEN_AFTER:
        return lambda p: p
    fit = _isotonic([(p, 1.0 if o > 0 else 0.0) for p, o in rows])
    xs, ys = [x for x, _ in fit], [y for _, y in fit]

    def apply(p: float) -> float:
        if p <= xs[0]:
            value = ys[0]
        elif p >= xs[-1]:
            value = ys[-1]
        else:
            i = bisect.bisect_right(xs, p)
            value = ys[i - 1] + (ys[i] - ys[i - 1]) * (p - xs[i - 1]) / (xs[i] - xs[i - 1])
        return min(P_CEIL, max(P_FLOOR, value))
    return apply


def calibrate(db: duckdb.DuckDBPyConnection, p: float) -> float:
    """One probability through the scored history. Fit once with `calibrator` when mapping many."""
    return calibrator(db)(p)


# ---- does learning from set-asides help? -------------------------------------------------------------------

LEARNING_MIN_N = 10        # scored calls needed in EACH group before a gap is worth saying: under it, "too early"
LEARNING_SAME_POINTS = 1.0  # a gap smaller than this many points reads as "about the same"
HIDDEN_LIKE = "change_reason like 'learned:%'"
_PLAIN = "Stocks we hid because of what you set aside"


def _rate(db, column: str, where: str) -> tuple[int, float | None]:
    n, rate = db.execute(f"select count(*), avg({_hit(column)}) from {LATEST} "
                         f"where {column} is not null and action = 'buy' and {where}").fetchone()
    return n, rate


def learning(db: duckdb.DuckDBPyConnection) -> dict:
    """Do the buys that learning demoted (change_reason 'learned: ...') do better or worse than the buys we showed?
    Per window: n of each group, each hit rate (beat the Nifty after costs and tax), the gap in points (hidden minus
    shown), a verdict (better, worse, same, too early) and one plain line. New buys only: adds on held stocks are never
    demoted. `lines` holds the three lines in window order."""
    out, lines = {}, []
    for column, _, label in WINDOWS:
        hn, hrate = _rate(db, column, HIDDEN_LIKE)
        sn, srate = _rate(db, column, "section = 'buy'")
        words = {"1m": "1 month", "3m": "3 months", "6m": "6 months"}[label]
        if hn < LEARNING_MIN_N or sn < LEARNING_MIN_N:
            verdict, gap = "too early", None
            line = f"Over {words}: too early to say whether hiding stocks like the ones you set aside helps (n={hn} and {sn}; we wait for {LEARNING_MIN_N} of each)."
        else:
            gap = round(100 * (hrate - srate), 1)
            verdict = "same" if abs(gap) < LEARNING_SAME_POINTS else "better" if gap > 0 else "worse"
            tail = f"(n={hn} and {sn}, over {words})."
            line = (f"{_PLAIN} did about the same {tail}" if verdict == "same"
                    else f"{_PLAIN} did {verdict} by {abs(gap):g} points {tail}")
        out[label] = {"hidden_n": hn, "shown_n": sn, "hidden_rate": hrate, "shown_rate": srate, "gap_points": gap,
                      "verdict": verdict, "line": line}
        lines.append(line)
    out["lines"] = lines
    return out
