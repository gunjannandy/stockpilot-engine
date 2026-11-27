"""Which model answers which kind of Job (decisions §2 Models): Haiku unless the kind says otherwise.

Forecasts and Analyse move to Sonnet only if the forecast bench says Haiku fails (the MODELS ticket
changes the lines below, nothing else)."""

DEFAULT_MODEL = "haiku"
MODEL_FOR_KIND: dict[str, str] = {}


def model_for(kind: str) -> str:
    return MODEL_FOR_KIND.get(kind, DEFAULT_MODEL)
