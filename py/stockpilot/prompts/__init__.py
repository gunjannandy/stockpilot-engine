"""Prompt files for the public model Jobs. A prompt is plain text; the brief follows it."""
from pathlib import Path

HERE = Path(__file__).parent


def load(name: str) -> str:
    return (HERE / f"{name}.md").read_text().strip()
