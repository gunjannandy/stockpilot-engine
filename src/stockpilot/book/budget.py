"""The monthly budget for new buys. The owners set it on the dashboard; it resets each calendar month.
The calls size buys from it and the Today tab shows it, both through `for_month`."""
import re
from datetime import date


def set_month(db, month: str, amount, by: str) -> None:
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", str(month)):
        raise ValueError(f"Month must look like 2026-12, not '{month}'.")
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount <= 0:
        raise ValueError("The budget must be a number above zero.")
    db.execute("insert or replace into budgets (month, amount_inr, set_by) values (?, ?, ?)", [month, float(amount), by])


def for_month(db, day: date, default: float) -> float:
    row = db.execute("select amount_inr from budgets where month = ?", [day.strftime("%Y-%m")]).fetchone()
    return row[0] if row else default
