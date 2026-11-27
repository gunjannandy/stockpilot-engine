"""One vocabulary for what a holding is. Stored rows say stock | mf | rsu; readers think equity | mf | foreign."""
from stockpilot.book import kinds


def test_every_stored_kind_has_one_reading():
    assert [kinds.canon(k) for k in ("stock", "mf", "rsu", "STOCK", None)] == ["equity", "mf", "foreign", "equity", ""]


def test_a_holding_priced_in_dollars_is_foreign_whatever_its_kind():
    assert kinds.is_foreign({"kind": "rsu"}) and kinds.is_foreign({"kind": "stock", "currency": "USD"})
    assert not kinds.is_foreign({"kind": "stock", "currency": "INR"}) and not kinds.is_foreign({"kind": "mf"})
