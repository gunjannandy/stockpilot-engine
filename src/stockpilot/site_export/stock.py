"""`data/stock/<SYMBOL>.json`: the key numbers, each with one plain sentence, for every stock the search box can open.
A block with nothing behind it is left out (the page hides the card); the reason belongs in the owner's Health tab."""
import json
from pathlib import Path
import re
import statistics
from datetime import date, datetime, time, timedelta

from stockpilot.site_export import plain, series
from stockpilot.site_export.io import write_json

QUARTERS_SHOWN, YEARS_SHOWN, MIN_YEARS = 8, 3, 2
DELIVERY_POINTS, DELIVERY_STALE_DAYS = 60, 10
OWNERSHIP_QUARTERS, OWNERSHIP_STALE_DAYS = 5, 400
LAST_MONTH, ITEMS_PER_BLOCK = 30, 8
ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6}


def _by_symbol(rows, key=0):
    out: dict = {}
    for r in rows:
        out.setdefault(r[key], []).append(r)
    return out


def _cr(x):
    return None if x is None else round(x / 1e7, 2)


def _growth(now, then):
    return round(now / then - 1, 4) if now is not None and then and then > 0 and now >= 0 else None


def fy_of(day: date) -> str:
    start = day.year if day.month >= 4 else day.year - 1
    return f"FY{start}-{(start + 1) % 100:02d}"


def load(db, as_of: date) -> dict:
    """Every table the stock files read, in a few bounded queries (a month, 60 days, 5 years of quarters)."""
    end = datetime.combine(as_of + timedelta(days=1), time.min)
    month_ago = datetime.combine(as_of - timedelta(days=LAST_MONTH), time.min)
    q = db.execute("""select symbol, period_end, revenue, net_profit from (
            select *, row_number() over (partition by symbol, period_end
                                         order by coalesce(consolidated, false) desc, filed_at desc) as rn
            from quarterly where filed_at < ? and period_end <= ? and period_end >= ?) where rn = 1
            order by symbol, period_end""", [end, as_of, as_of - timedelta(days=365 * 5)]).fetchall()
    return {
        "quarters": _by_symbol(q),
        "delivery": _by_symbol(db.execute(
            "select symbol, date, deliv_pct from delivery where series = 'EQ' and date <= ? and date >= ? and deliv_pct is not null "
            "order by symbol, date", [as_of, as_of - timedelta(days=95)]).fetchall()),
        "ownership": _by_symbol(db.execute(
            "select symbol, quarter_end, promoter_pct, pledge_pct from ownership where quarter_end <= ? and quarter_end >= ? "
            "and (filed_on is null or filed_on <= ?) order by symbol, quarter_end",
            [as_of, as_of - timedelta(days=OWNERSHIP_STALE_DAYS + 365), as_of]).fetchall()),
        "headlines": _by_symbol(db.execute(
            "select symbol, published_at, title, source, url from headlines where published_at >= ? and published_at < ? "
            "order by symbol, published_at desc, url", [month_ago, end]).fetchall()),
        "announcements": _by_symbol(db.execute(
            "select symbol, announced_at, subject from announcements where announced_at >= ? and announced_at < ? "
            "order by symbol, announced_at desc, subject", [month_ago, end]).fetchall()),
        "deals": _by_symbol(db.execute(
            "select symbol, date, kind, side, client, quantity, price from deals where date >= ? and date <= ? "
            "order by symbol, date desc, kind, client", [as_of - timedelta(days=LAST_MONTH), as_of]).fetchall()),
        "surveillance": dict(db.execute(
            "select symbol, label from surveillance where as_of = (select max(as_of) from surveillance where as_of <= ?)",
            [as_of]).fetchall()),
        "results": {s: (d, p) for s, d, p in db.execute(
            "select symbol, min(date), arg_min(purpose, date) from results_calendar where date >= ? group by symbol", [as_of]).fetchall()},
    }


def _quarters(rows):
    """Last eight quarters with growth on a year ago, then complete financial years summed from the quarters."""
    by_end = {r[1]: r for r in rows}
    ends = sorted(by_end)
    out = []
    for end in ends[-QUARTERS_SHOWN:]:
        _, _, sales, profit = by_end[end]
        if sales is None or profit is None:      # lane V: a filing without net profit (an insurer's) shows no quarter, never a null
            continue
        back = next((by_end[e] for e in ends if 360 <= (end - e).days <= 372), None)
        out.append({"period_end": str(end), "sales_cr": _cr(sales), "profit_cr": _cr(profit),
                    "sales_yoy": _growth(sales, back[2] if back else None), "profit_yoy": _growth(profit, back[3] if back else None)})
    years: dict = {}
    for end in ends:
        y = years.setdefault(fy_of(end), {"months": set(), "sales": 0.0, "profit": 0.0, "ok": True})
        _, _, sales, profit = by_end[end]
        y["months"].add(end.month)
        y["ok"] = y["ok"] and sales is not None and profit is not None
        y["sales"] += sales or 0
        y["profit"] += profit or 0
    full = [{"fy": fy, "quarters": 4, "sales_cr": _cr(y["sales"]), "profit_cr": _cr(y["profit"])}
            for fy, y in sorted(years.items()) if y["ok"] and y["months"] == {6, 9, 12, 3}][-YEARS_SHOWN:]
    return out, full


def _surveillance(label):
    m = re.search(r"\b(ASM|GSM)\b\D*?(\d+|[IVX]+)?\s*$", label or "", re.I)
    if not m:
        return None
    raw = (m.group(2) or "").upper()
    stage = int(raw) if raw.isdigit() else ROMAN.get(raw)
    return {"scheme": m.group(1).upper(), "stage": stage, "label": label, "sentence": plain.surveillance(m.group(1).upper(), stage)}


def _ownership(rows, as_of: date):
    """Promoter holding and pledge: the newest quarter, its move on the quarter before, and the last five quarters."""
    if not rows or (as_of - rows[-1][1]).days > OWNERSHIP_STALE_DAYS:
        return None
    rows = rows[-OWNERSHIP_QUARTERS:]
    trend = [{"quarter_end": str(q), "promoter_pct": round(p, 2), **({"pledge_pct": round(pl, 2)} if pl is not None else {})}
             for _, q, p, pl in rows]
    _, quarter, promoter, pledge = rows[-1]
    out = {"quarter_end": str(quarter), "promoter_pct": round(promoter, 2)}
    change = round(promoter - rows[-2][2], 2) if len(rows) > 1 else None
    if pledge is not None:
        out["pledge_pct"] = round(pledge, 2)
    if change is not None:
        out["change_pts"] = change
    out["trend"] = trend
    out["sentence"] = plain.ownership(promoter, change, pledge)
    return out


def build(symbol, name, industry, rows, as_of: date, data: dict, note=None) -> dict | None:
    """One stock's file, or None when it has no price at all."""
    if not rows:
        return None
    closes = [c for _, c, _ in rows]
    close, prev = closes[-1], closes[-2] if len(closes) > 1 else None
    year = closes[-series.DAY_RANGE:]
    low, high = min(year), max(year)
    position = round((close - low) / (high - low), 4) if high > low else 0.5
    out = {"symbol": symbol, "name": name or symbol, "industry": industry, "as_of": str(as_of), "close": round(close, 2),
           "prev_close": round(prev, 2) if prev else None, "change_pct": round(close / prev - 1, 4) if prev else None,
           "range52": {"low": round(low, 2), "high": round(high, 2), "position": position,
                       "sentence": plain.range52(close, low, high, position)}}
    last = rows[-1][2]
    if last:
        before = [v for _, _, v in rows[-21:-1] if v]
        avg = sum(before) / len(before) if len(before) >= 5 else None
        ratio = round(last / avg, 2) if avg else None
        out["volume"] = {"last": int(last), "avg_20d": round(avg) if avg else None, "ratio": ratio, "sentence": plain.volume(ratio)}
    dl = data["delivery"].get(symbol)
    if dl and (as_of - dl[-1][1]).days <= DELIVERY_STALE_DAYS:
        dl = dl[-DELIVERY_POINTS:]
        vals = [round(v, 1) for _, _, v in dl]
        avg = round(statistics.fmean(vals), 1)
        out["delivery"] = {"pct": vals[-1], "avg_pct": avg, "dates": [str(d) for _, d, _ in dl], "values": vals,
                           "sentence": plain.delivery(vals[-1], avg)}
    own = _ownership(data["ownership"].get(symbol), as_of)
    if own:
        out["ownership"] = own
    quarters, years = _quarters(data["quarters"].get(symbol, []))
    if quarters:
        out["quarters"], out["quarters_note"] = quarters, plain.quarters(quarters[-1])
    if len(years) >= MIN_YEARS:
        out["yearly"], out["yearly_note"] = years, plain.yearly(years[0], years[-1])
    heads = data["headlines"].get(symbol)
    if heads:
        out["headlines"] = [{"at": str(at), "title": t, "source": s, "url": u} for _, at, t, s, u in heads[:ITEMS_PER_BLOCK]]
        out["headlines_note"] = plain.headlines(len(heads))
    notes = data["announcements"].get(symbol)
    if notes:
        out["announcements"] = [{"at": str(at), "subject": s} for _, at, s in notes[:ITEMS_PER_BLOCK]]
        out["announcements_note"] = plain.announcements(len(notes))
    deals = data["deals"].get(symbol)
    if deals:
        out["deals"] = [{"date": str(d), "kind": k, "side": s, "client": c, "quantity": q, "price": p}
                        for _, d, k, s, c, q, p in deals[:ITEMS_PER_BLOCK]]
        out["deals_note"] = plain.deals(sum(1 for r in deals if r[3] == "buy"), sum(1 for r in deals if r[3] == "sell"))
    flag = _surveillance(data["surveillance"].get(symbol))
    if flag:
        out["surveillance"] = flag
    due = data["results"].get(symbol)
    if due:
        days = (due[0] - as_of).days
        out["results"] = {"next_on": str(due[0]), "purpose": due[1], "days_away": days, "sentence": plain.results(days, due[0])}
    if note:
        out["analyst_note"], out["analyst_note_bn"] = note
    return out


def analysed(db, day: date) -> dict:
    """{symbol: (summary, summary_bn)} for the stocks the analyst wrote about in the newest run, or answered an owner's ask
    about since (an answer newer than the run's day replaces the run's note)."""
    made = db.execute("select max(made_on) from calls where made_on <= ?", [day]).fetchone()[0]
    out = {}
    if made:
        for sym, reasons, bn in db.execute("select symbol, reasons, summary_bn from calls where made_on = ? "
                                           "qualify row_number() over (partition by symbol order by id desc) = 1 order by symbol", [made]).fetchall():
            text = (json.loads(reasons) if isinstance(reasons, str) else reasons or {}).get("summary")
            if text:
                out[sym] = (text, bn)
    for sym, answer in db.execute("select symbol, answer from analyst_asks where status = 'done' and answer is not null "
                                  "and (?::date is null or cast(done_at as date) >= ?::date) order by id", [made, made]).fetchall():
        a = json.loads(answer) if isinstance(answer, str) else answer or {}
        if a.get("summary"):
            out[sym] = (a["summary"], a.get("summary_bn") or None)
    return out


def write_all(db, out, exchanges, names, industries, as_of: date, day: date, reasoning=None) -> int:
    """History file and stock file for every symbol, a chunk of symbols at a time. Returns how many symbols had prices.
    `reasoning` (lane F1): a `reasoning.Book`; each stock file gets its object, built from the file's own sentences."""
    data, notes, n, written = load(db, as_of), analysed(db, day), 0, set()
    for sym, rows in series.chunks(db, exchanges, as_of):
        body = build(sym, names.get(sym), industries.get(sym), rows, as_of, data, notes.get(sym))
        if body is None:
            continue
        if reasoning is not None and (obj := reasoning.object(sym, stock=body)):
            body["reasoning"] = obj
        write_json(out, f"history/{sym}", series.history_file(sym, rows, as_of))
        write_json(out, f"stock/{sym}", body)
        written.add(sym)
        n += 1
    for sub in ("history", "stock"):        # files an earlier build wrote for a symbol that is no longer exported
        for old in (Path(out) / "data" / sub).glob("*.json"):
            if old.stem not in written:
                old.unlink()
    return n
