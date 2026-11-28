import json
from datetime import datetime

from stockpilot.jobs.news import impact, weights

NOW = datetime.fromisoformat("2026-11-28T10:00:00+05:30")


class Model:
    def __init__(self, answer):
        self.answer, self.prompts = answer, []

    def ask(self, prompt):
        self.prompts.append(prompt)
        return json.dumps(self.answer)


def it(i, source, n=1, link="https://x/a"):
    return {"id": i, "title": f"t{i}", "source": source, "published_at": "2026-11-28T09:00:00+05:30", "source_count": n, "link": link}


def test_source_weights_order_the_fixtures():  # C-082-1
    items = [it("blog", "Some Blog"), it("wire", "Reuters"), it("filing", "NSE"), it("wire2", "Mint", n=3)]
    assert [i["id"] for i in weights.rank_items(items, NOW)] == ["filing", "wire2", "wire", "blog"]
    assert [weights.source_weight(s) for s in ("BSE", "PTI", "randomblog.in")] == [3, 2, 1]


def test_sector_link_has_no_direction_and_one_row_per_item_and_stock():
    m = Model([{"id": "a", "touches": [
        {"symbol": "abc", "relation": "self", "direction": "good", "size": "large", "why_en": "w", "why_bn": "ব"},
        {"symbol": "XYZ", "relation": "sector", "direction": "bad", "size": "small"}]}])
    rows, answered = impact.judge([it("a", "NSE")], m, "2026-11-28T10:00:00+05:30")
    assert answered == ["a"]
    by = {r["symbol"]: r for r in rows}
    assert by["ABC"]["direction"] == "good" and not by["ABC"]["sector_only"] and by["ABC"]["id"] == "a:ABC"
    assert by["XYZ"]["direction"] is None and by["XYZ"]["sector_only"]


def test_high_impact_items_are_read_in_full_and_bad_answers_are_skipped():
    seen = []
    m = Model([{"id": "a", "touches": []}])
    impact.judge([it("a", "NSE"), it("b", "Some Blog")], m, "t", article=lambda link: seen.append(link) or "full text")
    assert seen == ["https://x/a"] and "ARTICLE: full text" in m.prompts[0]
    assert impact.judge([it("a", "NSE")], Model("garbage"), "t") == ([], [])
