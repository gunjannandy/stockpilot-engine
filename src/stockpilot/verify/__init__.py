"""Lane V: trust and verification. `sp verify` runs eleven checks against the store and the built site, writes
`docs/status/verify-<date>.md`, opens one GitHub issue per failed check, and exits non-zero on any hard failure.

Checks 1 to 6 are about the data on screen; 7 to 11 are about the forecast. Each check is a function `(ctx) -> Result`
in `data.py` or `model.py`. A check that cannot run (a missing file, an exception) fails: an unverified number is not a
trusted number."""
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

PASS, FAIL = "pass", "fail"


@dataclass
class Gap:
    area: str
    subject: str
    reason: str          # one of gaps.REASONS
    detail: str = ""


@dataclass
class Result:
    id: int
    name: str
    hard: bool = True
    status: str = PASS
    summary: str = ""
    numbers: dict = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)       # things worth reading that do not fail the check
    gaps: list[Gap] = field(default_factory=list)

    def fail(self, *problems: str) -> "Result":
        if problems:
            self.status = FAIL
            self.problems.extend(problems)
        return self

    @property
    def blocks(self) -> bool:
        """A hard failure: the deploy gate stops on it."""
        return self.status == FAIL and self.hard

    @property
    def label(self) -> str:
        return "pass" if self.status == PASS else ("FAIL (hard)" if self.hard else "soft fail")


@dataclass
class Ctx:
    db: object
    day: date
    site: Path | None = None            # a built site folder (the one that holds data/)
    previous_site: Path | None = None   # yesterday's, when the caller kept it
    briefs: Path | None = None          # folder of <day>.json briefs
    root: Path = Path(".")
    rules: object = None                # calls.decide.Rules
    budget_default: float = 100000.0
    liquidity_floor_cr: float = 1.0
    sector_index: dict = field(default_factory=dict)
    run_backtest: bool = True


def tolerance_ok(a, b, rel: float = 0.005, absolute: float = 0.0) -> bool:
    """`a` equals `b` within half a percent (the lane's tolerance), or within `absolute` for numbers near zero."""
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= max(rel * abs(b), absolute)


def run_all(ctx: Ctx, only: set[int] | None = None) -> list[Result]:
    from stockpilot.verify import data, model
    out = []
    for check in (data.check_numbers, data.check_units, data.check_prices, data.check_freshness, data.check_cross_source,
                  data.check_schema, model.check_bounds, model.check_calibration, model.check_rule_guards,
                  model.check_analyst_numbers, model.check_regression):
        number = CHECK_NUMBERS[check.__name__]
        if only and number not in only:
            continue
        try:
            out.append(check(ctx))
        except Exception as err:    # noqa: BLE001 - a check that crashes has verified nothing
            r = Result(number, NAMES[number], hard=number not in SOFT)
            out.append(r.fail(f"the check could not run: {type(err).__name__}: {str(err)[:300]}"))
    return out


CHECK_NUMBERS = {"check_numbers": 1, "check_units": 2, "check_prices": 3, "check_freshness": 4, "check_cross_source": 5,
                 "check_schema": 6, "check_bounds": 7, "check_calibration": 8, "check_rule_guards": 9,
                 "check_analyst_numbers": 10, "check_regression": 11}
SOFT = {8, 11}      # the lane marks 8 and 11 soft; check 3's exclusion and 5's tolerance are hard

NAMES = {1: "Every number on screen equals the DB", 2: "Units explained by lots equal Kite's units", 3: "Price sanity: no unexplained move over 40%",
         4: "Freshness: each source's newest row is within its allowed age", 5: "Cross-source: NSE vs BSE, index vs sectors, fund NAV vs holdings",
         6: "Schema: every contract field is present, typed and non-null", 7: "Bounds and determinism",
         8: "Calibration: backtest buckets have not drifted", 9: "Rule guards: Sell, Buy and number consistency",
         10: "Model sanity: numbers match the brief, evidence is cited", 11: "Regression: Sells do not flip run to run"}
