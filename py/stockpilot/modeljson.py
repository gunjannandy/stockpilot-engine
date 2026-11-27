"""Read the JSON a model answered with. Models wrap it in a ```json fence or a sentence; every parsed answer comes through here."""
import json
import re


def json_in(text) -> object:
    """The first JSON value in a model's answer. Raises ValueError (JSONDecodeError is one) when there is none."""
    text = str(text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
    if start < 0:
        raise ValueError("no JSON in the answer")
    return json.JSONDecoder().raw_decode(text[start:])[0]
