"""AUDIT #19 (lane ASKS): Holdings, Watchlist and Worth following had no writer after the migration, so they never changed and never
raised a yellow dot. Now the VM writes them (after Sync and after news is ranked) and a stock that enters or leaves is a change for both people."""
from stockpilot import list_writers
from stockpilot.jobs import wire
from test_wire import NOW, Rig


def row(symbol, exchange="NSE", reason="r", reason_bn="র"):
    return {"symbol": symbol, "exchange": exchange, "reason": reason, "reason_bn": reason_bn}


def cand(symbol, c3, c6, exchange="NSE"):
    return {"symbol": symbol, "exchange": exchange, "chance_3m": c3, "chance_6m": c6}


def members(rig, name):
    return [(r["symbol"], r["rank"]) for r in rig.db.execute("select * from lists where list_name = ? order by rank", [name])]


def marks(rig):
    return sorted((r["person"], r["symbol"], r["kind"], r["new_value"] or r["old_value"]) for r in rig.db.execute("select * from changes where kind like 'list_%'"))


def rig_with(holdings=(), watching=(), cands=()):
    rig = Rig()
    rig.deps.holdings = lambda: [row(s, reason="You hold this.") for s in holdings]
    rig.deps.watching = lambda: [row(s, reason="On the watchlist") for s in watching]
    rig.deps.candidates = lambda: [cand(*c) for c in cands]
    return rig


def refresh(rig, job="j1", now=None):
    return wire.refresh_lists(rig.deps, job, now or NOW)


def test_the_first_fill_writes_the_lists_without_a_flood_of_yellow_dots():
    rig = rig_with(holdings=["AAA", "BBB"], watching=["CCC"])
    refresh(rig)
    assert members(rig, "holdings") == [("AAA", 1), ("BBB", 2)] and members(rig, "watchlist") == [("CCC", 1)]
    assert marks(rig) == []


def test_a_stock_bought_or_added_later_is_a_yellow_change_for_both_people_and_one_sold_leaves_with_one():
    rig = rig_with(holdings=["AAA"], watching=["CCC"])
    refresh(rig)
    rig.deps.holdings = lambda: [row("AAA"), row("ZZZ", reason="You hold this.")]
    rig.deps.watching = lambda: []
    refresh(rig, "j2")
    assert marks(rig) == [("father", "CCC", "list_left", "watchlist"), ("father", "ZZZ", "list_entered", "holdings"),
                          ("owner", "CCC", "list_left", "watchlist"), ("owner", "ZZZ", "list_entered", "holdings")]
    assert members(rig, "watchlist") == []


def test_a_second_refresh_with_nothing_new_writes_nothing_and_keeps_since():
    rig = rig_with(holdings=["AAA"])
    refresh(rig)
    since = rig.db.execute("select since from lists where symbol = 'AAA'").fetchone()["since"]
    writes = rig.db.total_changes
    refresh(rig, "j2", NOW.replace(hour=11))
    assert rig.db.total_changes == writes and rig.db.execute("select since from lists where symbol = 'AAA'").fetchone()["since"] == since


def test_worth_following_is_the_best_unheld_candidates_ranked_by_both_chances():
    cands = [(f"S{n:02d}", 0.40 + n / 100, 0.40 + n / 100) for n in range(30)] + [("HELD", 0.99, 0.99)]
    rig = rig_with(holdings=["HELD"], cands=cands)
    refresh(rig)
    got = members(rig, "worth_following")
    assert [s for s, _ in got] == [f"S{n:02d}" for n in range(29, 19, -1)] and got[0][1] == 1      # ten, best first, the held one stays out
    first = rig.db.execute("select reason, reason_bn from lists where symbol = 'S29' and list_name = 'worth_following'").fetchone()
    assert "69%" in first["reason"] and first["reason_bn"]


def test_a_candidate_just_below_the_line_does_not_flap_in_and_out():
    cands = [(f"S{n:02d}", 0.40 + n / 100, 0.40 + n / 100) for n in range(30)]
    rig = rig_with(cands=cands)
    refresh(rig)
    cands2 = [(s, a, b) for s, a, b in cands if s != "S20"] + [("S20", 0.01, 0.01)]    # S20 (tenth) slips to last place, S19 moves up
    rig.deps.candidates = lambda: [cand(*c) for c in cands2]
    refresh(rig, "j2")
    kept = [s for s, _ in members(rig, "worth_following")]
    assert "S19" in kept and len(kept) <= 15 and "S20" not in kept
    assert [m for m in marks(rig) if m[2] == "list_left"] == [("father", "S20", "list_left", "worth_following"), ("owner", "S20", "list_left", "worth_following")]


def test_a_candidate_that_is_bought_enters_holdings_and_does_not_also_leave_worth_following_as_news():
    rig = rig_with(holdings=["ZZZ"], cands=[("AAA", 0.9, 0.9), ("BBB", 0.8, 0.8)])
    refresh(rig)
    rig.deps.holdings = lambda: [row("ZZZ"), row("AAA", reason="You hold this.")]
    refresh(rig, "j2")
    assert members(rig, "worth_following") == [("BBB", 1)]
    assert marks(rig) == [("father", "AAA", "list_entered", "holdings"), ("owner", "AAA", "list_entered", "holdings")]


def test_a_missing_source_leaves_that_list_alone():
    rig = rig_with(holdings=["AAA"])
    refresh(rig)
    rig.deps.holdings = lambda: None            # the store could not be read: never empty the list because of that
    refresh(rig, "j2")
    assert members(rig, "holdings") == [("AAA", 1)] and marks(rig) == []


def test_ranking_news_also_refreshes_the_lists_and_sync_does_after_it_finishes():
    rig = rig_with(holdings=["AAA"], cands=[("BBB", 0.7, 0.7)])
    rig.add("news_rank", {}, by="system"); rig.fire()
    assert members(rig, "holdings") == [("AAA", 1)] and members(rig, "worth_following") == [("BBB", 1)]
    ran = []
    inner = lambda ctx: ran.append(ctx) or "Done, 2 changes"
    rig.deps.holdings = lambda: [row("AAA"), row("NEW")]
    wrapped = wire.then_refresh_lists(inner, rig.deps)
    class Ctx:
        job = {"id": "sync1"}
        def progress(self, *a): pass
    assert wrapped(Ctx()) == "Done, 2 changes" and ("NEW", 2) in members(rig, "holdings")


def test_a_list_writer_that_breaks_never_fails_the_job_it_rides_on():
    rig = rig_with()
    rig.deps.holdings = lambda: 1 / 0
    wrapped = wire.then_refresh_lists(lambda ctx: "Done, no changes", rig.deps)
    class Ctx:
        job = {"id": "sync1"}
        def progress(self, *a): pass
    assert wrapped(Ctx()) == "Done, no changes"


def test_diff_is_pure():
    new, drop, marks_ = list_writers.diff("holdings", [row("A")], [], "j", "2026-11-26T10:00:00+05:30")
    assert [r["symbol"] for r in new] == ["A"] and drop == [] and marks_ == []
