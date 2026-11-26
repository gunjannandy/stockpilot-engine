"""T19: read one feedback message into asks (spec #24, Feedback). The father writes romanised Bengali with typos and often puts
several wishes in one message. One model call splits it into asks: original words, a plain English line, a plain Bengali line,
a tag, a size and a plan. CODE then picks the route, as the second judge: money and rule words, or a model flag, or a tag that
changes numbers (data, news, forecast) wait for the owner; wording, chart and no-change bug asks are built on a schedule.
This module reads and routes. It writes nothing: `rows` shapes the result for the `asks` table of the live contract."""
import re

ROLE = "feedback_read"
TAGS = ("chart", "data", "news", "forecast", "bug", "wording")
SIZES = ("small", "medium", "large")
ALWAYS_WAIT = {"forecast", "news", "data"}      # they change a call, a number or what is shown as fact
# Words that make an ask a money or rule change whatever the model says. "kite", "zerodha", "candle", "zoom" and "volume" are
# NOT here: "chart like Kite" names a look. Kite's read-only rule is caught by "read only" and "order".
_MONEY = (r"money|rupees?|rs|inr|lakh|crore|taka|taaka|tk|poisha|paisa|budget|stop[- ]?loss|threshold|rules?|tax(es)?|stcg|ltcg|"
          r"brokerage|orders?|read[- ]?only|allocation|sizing|probability|hurdle")
RISKY = re.compile(rf"(?<![\w])({_MONEY})(?![\w])", re.I)


class ReadError(Exception):
    """The reading failed; the job should fail visibly and the message stay unread."""


def risky(text: str) -> bool:
    return bool(RISKY.search(text or ""))


def route(ask: dict) -> str:
    safe = (ask["tag"] not in ALWAYS_WAIT and not ask.get("touches_money_or_rules")
            and not risky(f"{ask.get('original', '')} {ask.get('plan', '')} {ask.get('line_en', '')}"))
    return "auto" if safe else "owner_approval"


def _clean(raw: dict, message: str, n: int) -> dict:
    for key in ("line_en", "line_bn", "plan", "tag", "size"):
        if not str(raw.get(key) or "").strip():
            raise ReadError(f"ask {n} has no {key}")
    if raw["tag"] not in TAGS:
        raise ReadError(f"ask {n} has the tag {raw['tag']!r}; it must be one of {', '.join(TAGS)}")
    if raw["size"] not in SIZES:
        raise ReadError(f"ask {n} has the size {raw['size']!r}; it must be one of {', '.join(SIZES)}")
    original = str(raw.get("original") or "").strip()
    if not original or original.lower() not in message.lower():
        original = message.strip()          # the model paraphrased: quote the whole message rather than words he never wrote
    ask = {"original": original, "line_en": raw["line_en"].strip(), "line_bn": raw["line_bn"].strip(), "tag": raw["tag"],
           "size": raw["size"], "plan": raw["plan"].strip(), "touches_money_or_rules": bool(raw.get("touches_money_or_rules"))}
    ask.update(route=route(ask), status="understood", not_meant=False)
    return ask


def read(text: str, person: str, analyse, runners: list[str]) -> list[dict]:
    """The asks in one message, in the order written. Raises ReadError if the model fails or answers badly."""
    text = str(text or "").strip()
    if not text:
        raise ReadError("The message is empty.")
    try:
        got = analyse({"message": {"person": person, "text": text}}, ROLE, runners)["decisions"]
    except Exception as err:  # noqa: BLE001 - the runner's own errors, a bad parse: all mean "not read"
        raise ReadError(f"The model could not read the message: {err}") from err
    raw = got.get("asks") or []
    if not raw:
        raise ReadError("The model returned no asks.")
    return [_clean(a, text, i + 1) for i, a in enumerate(raw)]


def rows(feedback_id: str, asks: list[dict], now: str) -> list[dict]:
    """The `asks` table rows of the live contract, ids feedback_id_a1, _a2 and so on. `touches_money_or_rules` is not stored."""
    return [{"id": f"{feedback_id}_a{i}", "feedback_id": feedback_id, "original": a["original"], "line_en": a["line_en"],
             "line_bn": a["line_bn"], "tag": a["tag"], "size": a["size"], "plan": a["plan"], "route": a["route"],
             "status": "waiting_for_approval" if a["route"] == "owner_approval" else a["status"], "not_meant": False, "issue_number": None, "updated_at": now}
            for i, a in enumerate(asks, 1)]
