"""What a holding is. Writers store stock | mf | rsu (Kite, contract notes, Coin, Fidelity); readers use
equity | mf | foreign. This module is the only translation between the two."""

_CANON = {"stock": "equity", "equity": "equity", "share": "equity", "mf": "mf", "fund": "mf",
          "rsu": "foreign", "foreign": "foreign", "us": "foreign"}
FOREIGN_SQL = "(lower(kind) in ('rsu', 'foreign', 'us') or coalesce(currency, 'INR') <> 'INR')"


def canon(kind: str | None) -> str:
    k = (kind or "").lower()
    return _CANON.get(k, k)


def is_foreign(item: dict) -> bool:
    """Foreign shares (the RSUs): taxed as foreign, priced in dollars."""
    return canon(item.get("kind")) == "foreign" or (item.get("currency") or "INR") != "INR"
