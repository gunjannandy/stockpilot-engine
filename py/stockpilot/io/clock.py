"""IST clock helpers: the contract's times are ISO text with +05:30."""

from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def ist_now() -> datetime:
    return datetime.now(IST).replace(microsecond=0)


def ist_text(moment: datetime) -> str:
    return moment.astimezone(IST).replace(microsecond=0).isoformat()
