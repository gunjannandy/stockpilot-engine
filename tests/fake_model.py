"""A model stand-in that answers in the forecaster's schema: one item per stock in the brief it is handed."""


def item(symbol, p, **kw):
    base = {"symbol": symbol, "probability": p, "moved_by": [{"reason": "trend", "points": 3}], "risks": ["market"],
            "summary": f"{symbol} call.", "summary_bn": "সারাংশ।", "level_flag": None, "change_reason": None,
            "would_buy_if": None, "news_used": []}
    return {**base, **kw}


def fake_analyse(answers, seen, default=0.5):
    """`answers` maps role -> symbol -> probability; a stock it does not name gets `default`."""
    def analyse(brief, role, runners, **kw):
        seen.append((role, brief))
        return {"runner": "fake", "failures": [],
                "decisions": {"market_view": "Calm.", "market_view_bn": "শান্ত।",
                              "items": [item(s["symbol"], answers.get(role, {}).get(s["symbol"], default)) for s in brief["stocks"]]}}
    return analyse
