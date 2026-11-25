"""R11: learning from set-asides. Patterns from dismissals, the selection-only effect, forget and undo, and the record."""
import json
from datetime import date, datetime, timedelta

import pytest

from fake_worker import KEY, FakeWorker
from stockpilot import learn, store, vmqueue
from stockpilot.calls import decide
from stockpilot.sources import kite
from stockpilot.book import not_now
from stockpilot.calls.decide import Rules

DAY = date(2026, 11, 23)
RULES = Rules()


def cand(symbol, industry="Banks", adv=5.0, vol=0.40, close=300.0, **scores):
    s = {"momentum": 0.5, "quality": 0.5, "value": 0.5, "risk": 0.5, **scores}
    return {"symbol": symbol, "industry": industry, "scores": s, "flags": [],
            "metrics": {"adv_3m_cr": adv, "vol_1y": vol, "close": close}}


def screen_result(*extra):
    """Eight calm, large, other-industry stocks keep the medians honest; `extra` are the stocks under test."""
    base = [cand(f"BASE{i}", "IT", adv=80.0, vol=0.20) for i in range(8)]
    return {"as_of": DAY, "candidates": base + list(extra)}


def put(db, symbol, how="dismiss", scope="buy", days_ago=5, undone=False):
    when = datetime.combine(DAY - timedelta(days=days_ago), datetime.min.time())
    until = None if how == "dismiss" else DAY + timedelta(days=30)
    db.execute("insert into not_now (symbol, scope, until, set_by, set_at, undone_at, how) values (?, ?, ?, 'papa', ?, ?, ?)",
               [symbol, scope, until, when, when if undone else None, how])


def small_banks(n):
    return [cand(f"BANK{i}", "Banks", adv=1.0, vol=0.20) for i in range(n)]


def keys(db, result):
    return {p["pattern"] for p in learn.patterns(db, DAY, result)}


# ---- patterns ------------------------------------------------------------------------------------------

def test_three_dismissals_in_one_industry_make_a_pattern_and_two_do_not(db):
    result = screen_result(*small_banks(3))
    for i in range(2):
        put(db, f"BANK{i}")
    assert "industry:Banks" not in keys(db, result)
    put(db, "BANK2")
    found = {p["pattern"]: p for p in learn.patterns(db, DAY, result)}
    assert found["industry:Banks"]["dismissals"] == 3
    assert found["industry:Banks"]["text"] == "Fewer banks"


def test_a_pattern_must_cover_sixty_percent_of_the_dismissals(db):
    result = screen_result(*small_banks(3), cand("AUTO1", "Auto", adv=90, vol=0.2), cand("AUTO2", "Auto", adv=90, vol=0.2))
    for s in ("BANK0", "BANK1", "BANK2", "AUTO1", "AUTO2"):
        put(db, s)
    assert "industry:Banks" in keys(db, result)       # 3 of 5 = 60%
    put(db, "BASE1"), put(db, "BASE2")
    assert "industry:Banks" not in keys(db, result)   # 3 of 7 = 43%


def test_size_and_volatility_bands_make_patterns_too(db):
    jumpy = [cand(f"J{i}", f"Ind{i}", adv=90.0, vol=0.60) for i in range(3)]
    result = screen_result(*jumpy)
    for j in jumpy:
        put(db, j["symbol"])
    found = {p["pattern"]: p["text"] for p in learn.patterns(db, DAY, result)}
    assert found["vol:jumpy"] == "No jumpy stocks"
    assert "industry:Ind0" not in found


def test_a_small_size_band_is_plain_text(db):
    result = screen_result(*small_banks(3))
    for i in range(3):
        put(db, f"BANK{i}")
    assert {p["pattern"]: p["text"] for p in learn.patterns(db, DAY, result)}["size:small"] == "Fewer small stocks"


def test_a_snooze_counts_for_less_than_a_dismissal(db):
    result = screen_result(*small_banks(3))
    put(db, "BANK0"), put(db, "BANK1"), put(db, "BANK2", how="snooze")
    assert "industry:Banks" not in keys(db, result)       # 2 + half a snooze is under 3
    put(db, "BANK3", how="snooze")
    result = screen_result(*small_banks(4))
    found = {p["pattern"]: p for p in learn.patterns(db, DAY, result)}
    assert found["industry:Banks"]["dismissals"] == 2 and found["industry:Banks"]["snoozes"] == 2


def test_only_the_last_sixty_days_count(db):
    result = screen_result(*small_banks(3))
    put(db, "BANK0"), put(db, "BANK1"), put(db, "BANK2", days_ago=61)
    assert "industry:Banks" not in keys(db, result)


def test_a_sell_scope_set_aside_is_not_a_buy_preference(db):
    result = screen_result(*small_banks(3))
    for i in range(3):
        put(db, f"BANK{i}", scope="sell")
    assert keys(db, result) == set()


def test_the_same_stock_dismissed_for_two_scopes_counts_once(db):
    result = screen_result(*small_banks(3))
    put(db, "BANK0", scope="buy"), put(db, "BANK0", scope="any"), put(db, "BANK1")
    assert "industry:Banks" not in keys(db, result)


# ---- undo and forget ---------------------------------------------------------------------------------

def test_undoing_a_dismissal_removes_its_weight(db):
    result = screen_result(*small_banks(3))
    for i in range(3):
        put(db, f"BANK{i}")
    assert "industry:Banks" in keys(db, result)
    not_now.undo(db, db.execute("select min(id) from not_now").fetchone()[0])
    assert "industry:Banks" not in keys(db, result)


def test_forget_switches_a_pattern_off_for_90_days_then_it_may_return(db):
    result = screen_result(*small_banks(3))
    for i in range(3):
        put(db, f"BANK{i}")
    learn.forget(db, "industry:Banks", DAY)
    assert "industry:Banks" not in keys(db, result)
    payload = learn.payload(db, DAY, result)
    assert payload["forgotten"][0]["pattern"] == "industry:Banks" and payload["forgotten"][0]["until"] == str(DAY + timedelta(days=90))
    assert learn.forgotten(db, DAY + timedelta(days=90)) == {"industry:Banks"}
    assert learn.forgotten(db, DAY + timedelta(days=91)) == set()


def test_forgetting_twice_extends_and_a_bad_pattern_is_refused(db):
    learn.forget(db, "size:small", DAY)
    learn.forget(db, "size:small", DAY + timedelta(days=10))
    assert db.execute("select count(*), max(until) from learned_forgotten").fetchone() == (1, DAY + timedelta(days=100))
    for bad in ("", "colour:red", "industry:", None, 5):
        with pytest.raises(ValueError):
            learn.forget(db, bad, DAY)


def test_the_page_lists_each_pattern_with_its_dismissal_count_and_how_to_forget_it(db):
    result = screen_result(*small_banks(3))
    for i in range(3):
        put(db, f"BANK{i}")
    payload = learn.payload(db, DAY, result)
    row = next(p for p in payload["patterns"] if p["pattern"] == "industry:Banks")
    assert row["dismissals"] == 3 and row["forget"] == {"kind": "learned_forget", "pattern": "industry:Banks"}
    json.dumps(payload)


# ---- the effect: selection only ----------------------------------------------------------------------

def item(symbol, p, *, held=0, learned=None, **kw):
    base = {"symbol": symbol, "name": symbol, "industry": "Banks", "probability": p, "base_rate": 0.5, "base_rate_n": 800,
            "kind": "holding" if held else "candidate", "held_qty": held, "price": 100.0,
            "levels": {"entry": 100.0, "stop": 95.0, "target": 115.0, "why": "why"}, "adv_cr": 80.0, "hurdle": 0.014,
            "lots": [], "stop_hit": False, "buy_since": None, "summary": "s", "summary_bn": "s", "moved_by": [], "risks": [],
            "news_used": [], "level_flag": None, "change_reason": None, "would_buy_if": "", "learned": learned}
    base.update(kw)
    return base


def sections(items):
    out = decide.sections(items, rules=RULES, day=DAY, portfolio_value=1_000_000, sector_values={}, block_buys=None,
                          not_now=[], setasides={}, recent_sector_buys={})
    return {c["symbol"]: c for c in out["calls"]}


def test_a_matching_buy_is_demoted_to_the_follow_list_with_the_plain_line_and_is_not_removed():
    got = sections([item("SBIN", 0.60, learned="Fewer small banks"), item("TCS", 0.60)])
    assert got["TCS"]["section"] == "buy"
    c = got["SBIN"]
    assert c["section"] == "follow" and c["action"] == "watch"
    assert "Like stocks you set aside (Fewer small banks)" in c["warnings"]
    assert c["change_reason"] == "learned: Fewer small banks"
    assert c["quantity"] == 0 and c["amount"] == 0


def test_a_buy_ten_points_above_the_line_is_not_demoted():
    got = sections([item("A", RULES.buy_at + 0.10, learned="Fewer banks"), item("B", RULES.buy_at + 0.09, learned="Fewer banks")])
    assert got["A"]["section"] == "buy" and got["A"]["change_reason"] is None
    assert got["B"]["section"] == "follow"


def test_a_sell_and_a_trim_are_never_hidden_by_a_pattern():
    got = sections([item("LOW", 0.35, held=100, learned="Fewer banks"), item("BIG", 0.5, held=2000, learned="Fewer banks")])
    assert got["LOW"]["section"] == "sell" and got["BIG"]["section"] == "trim"
    assert "learned" not in (got["LOW"]["change_reason"] or "")


def test_a_held_stock_is_not_demoted_and_an_unmatched_buy_is_untouched():
    got = sections([item("HELD", 0.60, held=10, learned="Fewer banks"), item("FREE", 0.60)])
    assert got["HELD"]["section"] == "buy" and got["FREE"]["section"] == "buy"


def test_the_model_side_modules_never_import_learn():
    from pathlib import Path
    src = Path(learn.__file__).parent
    for name in ("calls/brief.py", "dossier.py", "calls/runner.py", "levels.py"):
        assert "learn" not in (src / name).read_text().replace("learned", ""), name


# ---- matching and the forecast integration -------------------------------------------------------------

def test_match_reads_the_stocks_own_features(db):
    result = screen_result(*small_banks(3), cand("BIGBANK", "Banks", adv=90.0, vol=0.2))
    for i in range(3):
        put(db, f"BANK{i}")
    found = learn.patterns(db, DAY, result)
    feats = learn.features(result)
    assert learn.match(found, feats["BANK0"])
    assert learn.match(found, feats["BIGBANK"]) == "Fewer banks"      # same industry, so the industry pattern fits
    assert learn.match([p for p in found if p["feature"] == "industry"], feats["BASE0"]) is None
    assert learn.match([], feats["BANK0"]) is None


# ---- the queue kind -----------------------------------------------------------------------------------

def item_q(id_, kind, payload, by="father"):
    return {"id": id_, "kind": kind, "payload": payload, "by": by, "at": "2026-11-23T08:00:00Z"}


def test_learned_forget_through_the_queue_and_a_bad_pattern_fails_with_a_note(db):
    w = FakeWorker(queue=[item_q("1", "learned_forget", {"pattern": "industry:Banks"}),
                          item_q("2", "learned_forget", {"pattern": "nonsense"})])
    try:
        vmqueue.poll(db, kite.Worker(w.url, KEY))
        acks = w.acks
    finally:
        w.close()
    assert db.execute("select pattern from learned_forgotten").fetchall() == [("industry:Banks",)]
    assert len(acks) == 2


def test_the_kinds_file_lists_learned_forget():
    kinds = json.loads((__import__("pathlib").Path(__file__).parent.parent / "schemas" / "queue-kinds.json").read_text())["kinds"]
    assert kinds["learned_forget"] == ["pattern"]
    assert "learned_forget" in vmqueue.HANDLERS


def test_the_new_table_is_in_a_backup_list():
    from stockpilot import backup
    assert "learned_forgotten" in backup.STATE_TABLES
