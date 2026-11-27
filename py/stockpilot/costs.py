"""What a trade costs and what a stock must earn to be worth it. Zerodha delivery charges, slippage that grows as a stock
gets thinner, short-term tax, the hurdle over the Nifty, and the expected gain in rupees.

Every rate here is a number the owners can check on Zerodha's charges page; they are constants, not config."""
import math
from datetime import date

from stockpilot.analysis import tax

STT = 0.001               # 0.1% on the buy and on the sell
STAMP_BUY = 0.00015       # 0.015% on the buy
EXCHANGE = 0.0000297      # 0.00297% on each side
SEBI_PER_CRORE = 10.0     # ₹10 per crore on each side
GST = 0.18                # on the exchange and SEBI charges
DP_SELL = 15.34           # the depository fee on each sell
SLIP_LIQUID, SLIP_THIN = 0.0005, 0.003    # per side: 0.05% at ₹50 crore a day or more, 0.3% at ₹1 crore or less
LIQUID_CR, THIN_CR = 50.0, 1.0


def charges(buy_value: float, sell_value: float) -> dict:
    """Brokerage is zero on delivery. Returns the rupees paid on the buy, on the sell, and in all."""
    def side(value, stt, extra):
        exchange, sebi = value * EXCHANGE, value / 1e7 * SEBI_PER_CRORE
        return value * stt + extra + exchange + sebi + GST * (exchange + sebi)
    buy = side(buy_value, STT, buy_value * STAMP_BUY)
    sell = side(sell_value, STT, DP_SELL)
    return {"buy": buy, "sell": sell, "total": buy + sell}


def slippage_rate(adv_cr: float | None) -> float:
    """Per side, between 0.05% (₹50 crore a day) and 0.3% (₹1 crore), straight on a log scale of liquidity."""
    if adv_cr is None or adv_cr <= THIN_CR:
        return SLIP_THIN
    if adv_cr >= LIQUID_CR:
        return SLIP_LIQUID
    share = math.log(adv_cr / THIN_CR) / math.log(LIQUID_CR / THIN_CR)
    return SLIP_THIN + (SLIP_LIQUID - SLIP_THIN) * share


def round_trip(value: float, adv_cr: float | None) -> dict:
    """Buy and sell the same rupee value: charges plus slippage both ways. `pct` is the share of the value."""
    c = charges(value, value)["total"]
    slip = 2 * slippage_rate(adv_cr) * value
    return {"charges": c, "slippage": slip, "total": c + slip, "pct": (c + slip) / value if value else 0.0}


def hurdle(round_trip_pct: float, nifty_3m: float, tax_rate: float) -> float:
    """How far past the Nifty a stock must run so that, after round-trip costs and the tax on its gain, the owners are no
    worse off than holding the index. The stock needs a gross gain g with g - c - t * (g - c) = nifty_3m."""
    gross = round_trip_pct + nifty_3m / (1 - tax_rate)
    return gross - nifty_3m


def hurdle_for(value: float, adv_cr: float | None, nifty_3m: float = 0.03, tax_rate: float | None = None) -> float:
    rate = tax.rules_for(tax.fy_of(date.today())).stcg_equity_rate if tax_rate is None else tax_rate
    return hurdle(round_trip(value, adv_cr)["pct"], nifty_3m, rate)


def expected_gain(quantity: float, entry: float, stop: float, target: float, p: float, adv_cr: float | None,
                  tax_rate: float | None = None) -> dict:
    """Expected rupees after costs and tax: quantity x entry x (p x upside - (1-p) x downside), less the round-trip costs,
    less short-term tax. Tax is due only on the winning branch, so it is p x rate x (the target's gain minus costs)."""
    rate = tax.rules_for(tax.fy_of(date.today())).stcg_equity_rate if tax_rate is None else tax_rate
    value = quantity * entry
    up, down = (target - entry) / entry, (entry - stop) / entry
    gross = value * (p * up - (1 - p) * down)
    cost = round_trip(value, adv_cr)["total"] if value else 0.0
    tax_due = p * rate * max(0.0, value * up - cost)
    return {"gross": gross, "costs": cost, "tax": tax_due, "net": gross - cost - tax_due}


def tax_if_sold(lots: list[dict], price: float, on: date) -> dict:
    """Capital-gains tax if every open lot were sold at `price` on `on`: lots with `acquired_on`, `quantity`, `cost` and
    `turns_long_term_on`. A short-term loss is set off against the long-term gain; a long-term loss only against long-term
    gains. The yearly long-term exemption is ignored, so the figure is an upper bound."""
    rules = tax.rules_for(tax.fy_of(on))
    short = long_ = 0.0
    for lot in lots:
        gain = (price - lot["cost"]) * lot["quantity"]
        if lot.get("turns_long_term_on") and on >= lot["turns_long_term_on"]:
            long_ += gain
        else:
            short += gain
    if short < 0:
        long_, short = long_ + short, 0.0
    long_ = max(0.0, long_) if long_ < 0 else long_
    return {"short_gain": short, "long_gain": long_,
            "tax": rules.stcg_equity_rate * max(0.0, short) + rules.ltcg_equity_rate * max(0.0, long_)}
