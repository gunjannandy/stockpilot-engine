"""The date range every Job takes: `--from` and `--to`, both days (YYYY-MM-DD), default today."""
import re
from dataclasses import dataclass
from datetime import date

_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class DateRange:
    start: date
    end: date

    def days(self) -> list[date]:
        return [date.fromordinal(n) for n in range(self.start.toordinal(), self.end.toordinal() + 1)]

    def __str__(self) -> str:
        return f"{self.start}..{self.end}"


def _day(text: str, what: str) -> date:
    if not _DAY.match(text):
        raise ValueError(f"{what} must be a day like 2026-11-27, not {text!r}")
    return date.fromisoformat(text)


def parse_range(start: str | None, end: str | None, today: date) -> DateRange:
    first = _day(start, "from") if start else (_day(end, "to") if end else today)
    last = _day(end, "to") if end else first
    if first > last:
        raise ValueError(f"the range ends ({last}) before it starts ({first})")
    return DateRange(first, last)
