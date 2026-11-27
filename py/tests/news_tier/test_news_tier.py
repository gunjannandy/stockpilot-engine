"""T18: tag news in batches, spread privately to holdings and watchlist, rank, tier, cap Sonnet refreshes. Fake model only."""
import ast
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from stockpilot import jobrun, news_rank, news_tag

IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 11, 25, 11, 0, tzinfo=IST)
SRC = Path(__file__).resolve().parents[2] / "stockpilot"


def item(i, impact=3, hours=1, sources=1, sector="Banks", direction="good", touches=(("AAA", "self"),)):
    return {"id": f"n{i}", "title": f"Event {i}", "source": "ET", "source_count": sources, "sector": sector,
            "published_at": (NOW - timedelta(hours=hours)).isoformat(timespec="seconds"), "direction": direction,
            "impact": impact, "line_en": "Plain line.", "line_bn": "সহজ লাইন।",
            "touches": [{"symbol": s, "exchange": "NSE", "relation": r, "direction": direction, "size": "large",
                         "changes_call": True} for s, r in touches]}


class TagModel:
    """Answers the tagging prompt with one tag per id it is shown."""
    def __init__(self, fail_first=False):
        self.prompts, self.fail_first = [], fail_first

    def ask(self, prompt):
        self.prompts.append(prompt)
        if self.fail_first and len(self.prompts) == 1:
            raise RuntimeError("gemini down")
        ids = [ln.split("|")[0] for ln in prompt.splitlines() if ln.startswith("id:")]
        ids = [i[3:] for i in ids]
        return json.dumps([{"id": i, "sector": "Banks", "direction": "good", "impact": 4, "line_en": "Line.",
                            "line_bn": "লাইন।", "touches": [{"symbol": "AAA", "exchange": "NSE", "relation": "self",
                                                              "direction": "good", "size": "large", "changes_call": True}]} for i in ids])


# --- tagging --------------------------------------------------------------------------------------------
def test_tags_in_batches_of_about_10():
    raw = [{"id": f"n{i}", "title": f"T{i}", "source": "ET"} for i in range(65)]
    model = TagModel()
    tags = news_tag.tag_all(raw, model)
    assert [len(b) for b in news_tag.batches(raw)] == [10] * 6 + [5]
    assert len(model.prompts) == 7 and len(tags) == 65


def test_second_model_takes_over_when_the_first_fails():
    first, second = TagModel(fail_first=True), TagModel()
    tags = news_tag.tag_all([{"id": "n1", "title": "T", "source": "ET"}], first, fallback=second)
    assert len(tags) == 1 and len(second.prompts) == 1


def test_tagging_prompt_has_public_news_only_and_clamps_bad_impact():
    class Bad(TagModel):
        def ask(self, prompt):
            return json.dumps([{"id": "n1", "sector": "Banks", "direction": "good", "impact": 9, "line_en": "L",
                                "line_bn": "ল", "touches": []}])
    tag = news_tag.tag_all([{"id": "n1", "title": "T", "source": "ET"}], Bad())[0]
    assert tag["impact"] == 5
    src = (SRC / "news_tag.py").read_text()
    assert "holding" not in src.lower() and "watchlist" not in src.lower()


# --- spreading is private ---------------------------------------------------------------------------------
def test_spread_matches_holdings_watchlist_then_sector_then_other():
    sector_map = {"AAA": "Banks", "BBB": "Banks", "CCC": "IT", "DDD": "Banks"}
    rows = news_rank.spread([item(1, touches=(("AAA", "self"),)), item(2, touches=(("ZZZ", "self"),), sector="Banks"),
                             item(3, touches=(("YYY", "self"),), sector="Metals")],
                            holdings={"AAA"}, watchlist={"CCC"}, sector_map=sector_map)
    by = {(r["item_id"], r["symbol"]): r["closeness"] for r in rows}
    assert by[("n1", "AAA")] == "holding"
    assert by[("n2", "AAA")] == "sector"      # touches no list stock, but a holding shares its sector
    assert not any(r["item_id"] == "n3" for r in rows)


def test_rank_is_impact_x_closeness_x_freshness_x_sources():
    base = news_rank.score(impact=4, closeness="holding", age_hours=1, sources=2)
    assert base > news_rank.score(impact=4, closeness="watchlist", age_hours=1, sources=2)
    assert news_rank.score(impact=4, closeness="watchlist", age_hours=1, sources=2) > news_rank.score(impact=4, closeness="sector", age_hours=1, sources=2)
    assert base > news_rank.score(impact=2, closeness="holding", age_hours=1, sources=2)
    assert base > news_rank.score(impact=4, closeness="holding", age_hours=30, sources=2)
    assert base > news_rank.score(impact=4, closeness="holding", age_hours=1, sources=1)


def test_private_module_is_not_imported_by_public_code_and_job_runs_private():
    contract = json.loads((SRC.parents[1] / "schemas" / "live-contract.json").read_text())
    assert contract["job_kinds"]["news_rank"]["runs_on"] == "vm_private"
    for p in SRC.rglob("*.py"):
        if p.name in ("news_rank.py",):
            continue
        for node in ast.walk(ast.parse(p.read_text())):
            names = [a.name for a in node.names] if isinstance(node, (ast.Import, ast.ImportFrom)) else []
            mod = getattr(node, "module", "") or ""
            if "news_rank" in mod or any("news_rank" in n for n in names):
                assert p.name in ("news_refresh.py", "__init__.py", "jobrun.py") or "jobs" in str(p), p


# --- tiers and marks ---------------------------------------------------------------------------------------
def test_each_tier_makes_the_right_mark():
    held, watch = {"AAA"}, {"CCC"}
    sm = {"AAA": "Banks", "CCC": "IT"}
    high = news_rank.rank([item(1, impact=5)], held, watch, sm, NOW)[0]
    med = news_rank.rank([item(2, impact=3)], held, watch, sm, NOW)[0]
    low = news_rank.rank([item(3, impact=1)], held, watch, sm, NOW)[0]
    other = news_rank.rank([item(4, impact=5, touches=(("QQQ", "self"),), sector="Metals")], held, watch, sm, NOW)
    assert (high["tier"], news_rank.mark(high)) == ("high", "yellow_dot")
    assert (med["tier"], news_rank.mark(med)) == ("medium", "yellow_dot")
    assert (low["tier"], news_rank.mark(low)) == ("low", "newspaper")
    assert other == []                      # news on no held, watched or same-sector stock is not ranked for the owners


def test_job_handlers_tag_and_rank_with_a_fake_model():
    r = jobrun.JobRunner(jobrun.MemorySink(), model=TagModel(), clock=lambda: NOW)
    r.register("news_tag", news_tag.handler(lambda tags: saved.extend(tags)))
    saved = []
    jid = r.enqueue("news_tag", {"batch": [{"id": "n1", "title": "T", "source": "ET"}]}, asked_by="system")
    r.run(jid)
    assert r.sink.jobs[jid]["status"] == "done" and len(saved) == 1
    out = []
    r.register("news_rank", news_rank.handler(lambda: ([item(1, impact=5)], {"AAA"}, set(), {"AAA": "Banks"}, NOW), out.extend))
    jid = r.run(r.enqueue("news_rank", {}, asked_by="system"))
    assert r.sink.jobs[jid]["status"] == "done" and out[0]["tier"] == "high"


def test_high_impact_off_the_lists_is_not_high():
    r = news_rank.rank([item(1, impact=5, touches=(("BBB", "self"),))], {"AAA"}, set(), {"AAA": "Banks", "BBB": "Banks"}, NOW)[0]
    assert r["closeness"] == "sector" and r["tier"] == "medium"


# --- the caps ---------------------------------------------------------------------------------------------
def test_burst_of_high_impact_keeps_sonnet_at_2_at_once_and_6_a_day():
    gov = news_rank.SonnetGovernor(day=NOW.date())
    picked = [gov.start(f"S{i}", NOW) for i in range(10)]
    assert picked == ["sonnet"] * 2 + ["cheap"] * 8        # 2 at once; the rest take the cheap route
    assert len(gov.running) == 2
    gov.finish("S0"); gov.finish("S1")
    more = [gov.start(f"T{i}", NOW) for i in range(10)]
    assert more.count("sonnet") == 2 and gov.used_today == 4   # two slots freed, two more taken
    gov.finish("T0"); gov.finish("T1")
    last = [gov.start(f"U{i}", NOW) for i in range(5)]
    assert last.count("sonnet") == 2 and gov.used_today == 6   # the day's 6 are spent
    gov.finish("U0"); gov.finish("U1")
    assert gov.start("late", NOW) == "cheap" and gov.used_today == 6


def test_daily_cap_resets_next_day_and_same_stock_is_not_refreshed_twice():
    gov = news_rank.SonnetGovernor(day=NOW.date())
    for i in range(6):
        gov.start(f"S{i}", NOW); gov.finish(f"S{i}")
    assert gov.start("S9", NOW) == "cheap"
    assert gov.start("S9", NOW + timedelta(days=1)) == "sonnet"
    gov2 = news_rank.SonnetGovernor(day=NOW.date())
    assert gov2.start("X", NOW) == "sonnet" and gov2.start("X", NOW) == "skip"


def test_refresh_plan_burst_with_fake_model():
    held = {f"S{i}" for i in range(10)}
    sm = {s: "Banks" for s in held}
    items = [item(i, impact=5, touches=((f"S{i}", "self"),)) for i in range(10)]
    ranked = news_rank.rank(items, held, set(), sm, NOW)
    plan = news_rank.refresh_plan(ranked, news_rank.SonnetGovernor(day=NOW.date()), NOW)
    models = [p["model"] for p in plan]
    assert models.count("sonnet") == 2 and all(m in ("sonnet", "cheap") for m in models) and len(plan) == 10
    assert {p["mark"] for p in plan} == {"yellow_dot"}
