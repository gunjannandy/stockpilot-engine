"""The Saturday analysis: fund review, opportunities, allocation and tax. Each section is independent: one
failing becomes a problem row and the run ends 'partial'. Reports are stored for the dashboard to read."""
import csv
import json
import traceback
from datetime import date
from pathlib import Path

import duckdb
import yaml

from stockpilot.book import kinds
from stockpilot import gaps, journal, valuation
from stockpilot.analysis import allocation, fundreview, opportunities, tax
from stockpilot.sources import fx


def load_private(root: Path) -> dict:
    """Owner facts from private/: target allocation, carried-forward losses, salary income, 31 Jan 2018 prices."""
    out = {"target": None, "carried": [], "slab_income": 0.0, "fmv_2018": {}}
    profile = root / "private" / "profile.yaml"
    if profile.exists():
        data = yaml.safe_load(profile.read_text()) or {}
        out["target"] = data.get("target_allocation")
        out["carried"] = data.get("carried_losses") or []
        out["slab_income"] = float(data.get("taxable_income_ex_gains") or 0)
    fmv = root / "private" / "fmv_2018.csv"
    if fmv.exists():
        with fmv.open() as f:
            out["fmv_2018"] = {r["isin"]: float(r["price"]) for r in csv.DictReader(f)}
    return out


def _lots(db) -> list[dict]:
    cols = ["id", "kind", "symbol", "isin", "acquired_on", "quantity", "cost_per_unit", "currency"]
    lots = [dict(zip(cols, r)) for r in db.execute(f"select {','.join(cols)} from lots").fetchall()]
    for lot in lots:
        if kinds.canon(lot["kind"]) == "mf":
            fund = valuation.fund_for(db, lot["isin"])
            lot["bucket"] = tax.mf_bucket(fund[4] if fund else None, lot["acquired_on"], fund[1] if fund else "")
    return lots


def _sales(db) -> list[dict]:
    cols = ["kind", "symbol", "isin", "sold_on", "quantity", "price_per_unit", "currency", "expenses"]
    return [dict(zip(cols, r)) for r in db.execute(f"select {','.join(cols)} from sales").fetchall()]


def _closes(db, symbols, year) -> dict:
    out: dict[str, dict] = {}
    for symbol in symbols:
        rows = db.execute("select date, close from prices where symbol = ? and exchange in ('NYSE','NASDAQ','US') "
                          "and date between ? and ?", [symbol, date(year, 1, 1), date(year, 12, 31)]).fetchall()
        if rows:
            out[symbol] = dict(rows)
    return out


def console_notes(db, lots, sales, fy: int, rate_on) -> list[str]:
    """Stage 7 check: our gains for the last financial year Zerodha Console has a tax P&L for, against Console's.
    Plain-words notes only; any failure here is a note, never a failed tax section."""
    from stockpilot.trades import consolepnl
    try:
        have = {r[0] for r in db.execute("select fy from console_pnl_totals").fetchall()}
        year = next((y for y in (fy, fy - 1) if f"{y}-{str(y + 1)[-2:]}" in have), None)
        if year is None:
            return []
        return consolepnl.check(db, year, tax.realise(lots, sales, {}, rate_on))
    except Exception as err:   # noqa: BLE001 - a check must not stop the tax section
        return [f"The check against Console's tax P&L could not run: {err}"]


def itr_notes(db, lots, sales, fy: int, rate_on) -> list[str]:
    """Stage 7 check: the last filed income tax return (this financial year's, else last year's) against Console's tax
    P&L and our lots. Plain-words notes only; any failure here is a note, never a failed tax section."""
    from stockpilot.trades import itr
    try:
        have = {r[0] for r in db.execute("select assessment_year from itr_documents where coalesce(for_owner, true)").fetchall()}
        year = next((y for y in (fy, fy - 1) if f"{y + 1}-{str(y + 2)[-2:]}" in have), None)
        if year is None:
            return []
        foreign = sum(1 for lot in lots if kinds.is_foreign(lot) and lot["acquired_on"] <= date(year, 12, 31))
        return itr.check(db, year, tax.realise(lots, sales, {}, rate_on), foreign_lots=foreign)
    except Exception as err:   # noqa: BLE001 - a check must not stop the tax section
        return [f"The check against the income tax return could not run: {err}"]


def fidelity_notes(db) -> list[str]:
    """Stage 7 check: the ServiceNow vests and sales in Fidelity's documents against the ones we hold. Plain-words notes
    only; any failure here is a note, never a failed tax section."""
    from stockpilot.trades import fidelity_docs
    try:
        return fidelity_docs.reconcile(db).notes
    except Exception as err:   # noqa: BLE001 - a check must not stop the tax section
        return [f"The check against Fidelity's statements could not run: {err}"]


def tax_section(db, as_of: date, out_dir: Path, private: dict) -> dict:
    fy = tax.fy_of(as_of)
    lots, sales = _lots(db), _sales(db)
    rate_on = fx.rate_on(db)
    foreign = {l["symbol"] for l in lots if kinds.is_foreign(l)}
    pack = tax.build_pack(lots, sales, fy, Path(out_dir) / tax.fy_label(fy), rate_on, _closes(db, foreign, fy),
                          private["fmv_2018"], private["carried"], private["slab_income"],
                          fx_note=fx.source_note(db, date(fy, 12, 31)) if foreign else "")
    summary = pack["summary"]
    left = tax.open_lots(lots, sales)
    prices = {l["symbol"]: valuation.unit_price_inr(db, l, as_of) for l in left if tax.bucket_of(l) == "equity"}
    harvest = tax.harvest(left, {s: p for s, p in prices.items() if p}, as_of, tax.rules_for(fy),
                          realised_ltcg_equity=summary["ltcg_equity"])
    notes = list(summary["warnings"])
    notes += console_notes(db, lots, sales, fy, rate_on)
    notes += itr_notes(db, lots, sales, fy, rate_on)
    notes += fidelity_notes(db)
    if not private["slab_income"]:
        notes.append("Salary income is not on file, so the tax figure covers capital gains only.")
    expected = db.execute("select trade_date, quantity, symbol from trades where status = 'expected' "
                          "and side = 'vest' order by trade_date").fetchall()
    return {**summary, "warnings": notes, "harvest": harvest, "schedule_fa": pack["schedule_fa"],
            "pack_dir": pack["dir"], "as_of": as_of,
            "expected_vests": [{"on": d, "quantity": q, "symbol": s} for d, q, s in expected]}


def refresh_expected_vests(db, as_of: date, months_ahead: int = 6) -> int:
    """Project the next RSU vests from the confirmed ones and store them as 'expected'. They never become lots:
    a vest is real only when a Fidelity email, payslip or Form 16 confirms it."""
    from datetime import timedelta
    from stockpilot.trades import corporate_actions, lots, rsu
    cols = "source, source_ref, kind, symbol, isin, side, trade_date, quantity, price, currency, status, trade_key"
    confirmed = [lots.Trade(*r) for r in db.execute(
        f"select {cols} from trades where side = 'vest' and status = 'confirmed'").fetchall()]
    actions = [corporate_actions.Action(*r) for r in db.execute(
        "select symbol, isin, ex_date, kind, numerator, denominator, subject from corporate_actions").fetchall()]
    db.execute("delete from trades where status = 'expected' and source_ref like 'expected:%'")
    return lots.save_trades(db, rsu.expected_vests(confirmed, as_of + timedelta(days=30 * months_ahead), actions))


def _money(x) -> str:
    return f"₹{abs(x):,.0f}"


def store_section(db, as_of: date, name: str, payload: dict) -> None:
    """Keep one weekly section as built; the dashboard reshapes it when the site is built (site.weekly_view)."""
    db.execute("insert or replace into weekly_reports values (?, ?, ?)", [as_of, name, json.dumps(payload, default=str)])


def run(db: duckdb.DuckDBPyConnection, as_of: date, out_dir: Path | str, target: dict | None = None,
        liquidity_floor_cr: float = 1.0, private: dict | None = None) -> dict:
    private = {**{"carried": [], "slab_income": 0.0, "fmv_2018": {}}, **(private or {})}
    run_id = journal.start(db, "weekly")
    try:
        refresh_expected_vests(db, as_of)       # before the tax section, which lists them
    except Exception as err:
        journal.problem(db, "weekly", f"expected vests: {err!r}")
    sections = {
        "funds": lambda: {"as_of": as_of, "funds": fundreview.review(db, as_of)},
        "opportunities": lambda: opportunities.weekly(db, as_of, liquidity_floor_cr),
        "allocation": lambda: allocation.compare(db, as_of, target),
        "tax": lambda: tax_section(db, as_of, Path(out_dir), private),
        "gaps": lambda: {"note": gaps.weekly_note(db), "gaps": [{k: str(v) for k, v in g.items()} for g in gaps.open_gaps(db)]},
    }
    failed = {}
    for name, build in sections.items():
        try:
            payload = build()
            store_section(db, as_of, name, payload)
        except Exception as err:
            failed[name] = f"{err}"
            journal.problem(db, "weekly", f"{name}: {err!r}\n{traceback.format_exc(limit=3)}", "error")
    status = "ok" if not failed else "partial"
    journal.finish(db, run_id, status, {"failed": failed})
    return {"status": status, "failed": failed}
