"""One plain sentence per metric, from fixed rules. No model writes any of these. Words the father does not use
(averages by length, exchange scheme names, stages) never appear: see PRODUCT.md."""


def inr(x: float) -> str:
    return f"₹{x:,.0f}" if abs(x) >= 100 else f"₹{x:,.2f}"


def crore(x: float) -> str:
    return f"₹{x:,.0f} crore" if abs(x) >= 100 else f"₹{x:,.1f} crore"


def _pct(x: float) -> str:
    return f"{abs(x) * 100:.0f}%" if abs(x) >= 0.095 else f"{abs(x) * 100:.1f}%"


def range52(close, low, high, position) -> str:
    where = ("close to the top of" if position >= 0.9 else "in the upper part of" if position >= 0.65 else
             "about halfway through" if position >= 0.35 else "in the lower part of" if position > 0.1 else "close to the bottom of")
    return f"The price is {where} its 1-year range ({inr(low)} to {inr(high)}), at {position * 100:.0f}% of the way up."


def volume(ratio) -> str:
    if ratio is None:
        return "Shares traded today; there is not enough history to say whether that is usual."
    if ratio >= 2:
        return f"Trading {ratio:.1f} times its usual volume today: unusual interest, up or down."
    if ratio <= 0.5:
        return "Very quiet today: well under its usual trading."
    return "Trading about as much as usual today."


def delivery(pct, avg) -> str:
    base = f"{pct:.0f}% of the shares traded were taken home, not sold again the same day"
    if avg is None:
        return base + ". A high share means buyers plan to keep them."
    return base + (f"; the usual share is {avg:.0f}%." if abs(pct - avg) >= 3 else ", about the usual share.")


def ownership(promoter, change, pledge) -> str:
    out = f"Promoters (the founding owners) hold {_p(promoter)}% of the company"
    if change is not None:
        out += ", about the same as last quarter" if abs(change) < 0.1 else f", {'up' if change > 0 else 'down'} {abs(change):.1f} points from last quarter"
    if pledge is None:
        return out + "."
    if pledge <= 0:
        return out + "; none of their shares are pledged for loans."
    return out + f"; {_p(pledge)}% of their shares are pledged for loans" + (", which is high." if pledge >= 20 else ".")


def _p(x) -> str:
    return f"{x:.1f}".removesuffix(".0")


def quarters(last) -> str:
    sy, py = last.get("sales_yoy"), last.get("profit_yoy")
    if sy is None:
        return f"Latest quarter: sales {crore(last['sales_cr'])}, profit {crore(last['profit_cr'])}."
    s = f"Sales {'grew' if sy >= 0 else 'fell'} {_pct(sy)} from a year ago"
    if py is None:
        return s + "."
    return s + f", and profit {'rose' if py >= 0 else 'fell'} {_pct(py)}."


def yearly(first, last) -> str:
    a, b = first["profit_cr"], last["profit_cr"]
    word = "rose" if b > a else "fell" if b < a else "stayed the same"
    return f"Yearly profit {word} from {crore(a)} in {first['fy']} to {crore(b)} in {last['fy']}."


def headlines(n) -> str:
    return f"{n} news item{'' if n == 1 else 's'} in the last month."


def announcements(n) -> str:
    return f"{n} company notice{'' if n == 1 else 's'} to the exchange in the last month."


def deals(buys, sells) -> str:
    n = buys + sells
    return (f"{n} large deal{'' if n == 1 else 's'} in the last month: {buys} buying and {sells} selling. "
            "Big buyers or sellers can move the price.")


def surveillance(scheme, stage) -> str:
    level = f" (level {stage})" if stage else ""
    if scheme == "GSM":
        return f"The exchange keeps a close watch on this stock for unusual price swings{level}. Take extra care."
    return f"The exchange has put this stock on a short list for sharp price swings{level}. Take extra care."


def results(days_away, on) -> str:
    when = "today" if days_away == 0 else "tomorrow" if days_away == 1 else f"in {days_away} days"
    return f"Next results are expected on {on:%d %b}, {when}."


def index_line(name, month, year) -> str:
    def move(x, span):
        return f"{'up' if x >= 0 else 'down'} {_pct(x)} over {span}"
    parts = [move(x, s) for x, s in ((month, "the last month"), (year, "the year")) if x is not None]
    return f"{name} is {' and '.join(parts)}." if parts else f"{name}: not enough history yet."


def vix(level) -> str:
    mood = "calm" if level < 15 else "nervous" if level > 20 else "a little uneasy"
    return f"India VIX is {level:.1f}. It measures how much traders expect the market to swing; the market looks {mood}."


def flows(days, fii, dii) -> str:
    def side(name, net):
        return f"{name} {'bought' if net >= 0 else 'sold'} {crore(abs(net))} more than they {'sold' if net >= 0 else 'bought'}"
    parts = [side(n, v) for n, v in (("foreign funds", fii), ("Indian funds", dii)) if v is not None]
    span = "on the last day" if days <= 1 else f"over the last {days} trading days"
    return f"{span.capitalize()}, " + " and ".join(parts) + "." if parts else "No fund flow numbers yet."


def trades(closed, winners, total) -> str:
    if not closed:
        return "No closed trades yet."
    s = f"{winners} of {closed} closed trades made money"
    return s + f"; together they {'gained' if total >= 0 else 'lost'} {inr(abs(total))}."


def outcomes(n, hit3) -> str:
    if not n:
        return "No call has a result yet. The first ones are scored a month after they are made."
    s = f"{n} call{'' if n == 1 else 's'} {'has' if n == 1 else 'have'} a result."
    return s + (f" At 3 months, {hit3 * 100:.0f}% beat the Nifty after costs and tax." if hit3 is not None else "")


def since(new, changed, dropped, moved) -> str:
    bits = [f"{len(x)} {w}" for x, w in ((new, "new"), (changed, "changed"), (dropped, "dropped"), (moved, "with a moved chance")) if x]
    return "Since last time: " + ", ".join(bits) + "." if bits else "Nothing has changed since last time."
