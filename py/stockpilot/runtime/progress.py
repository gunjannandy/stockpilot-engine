"""Progress lines: append-only, numbered from 1 with no gaps, one JSON object per line on stdout.

The Action's log is the record; the Worker only needs the Job's start and end. A writer never edits a line.
"""
import json
import sys
from dataclasses import dataclass, field
from typing import TextIO

from stockpilot.io.clock import ist_now, ist_text

STATES = ("info", "ok", "fail")


@dataclass
class Progress:
    run_id: str
    out: TextIO = field(default_factory=lambda: sys.stdout)
    seq: int = 0

    def line(self, text: str, state: str = "info", text_bn: str | None = None) -> dict:
        if state not in STATES:
            raise ValueError(f"unknown progress state {state!r}")
        self.seq += 1
        row = {"run_id": self.run_id, "seq": self.seq, "at": ist_text(ist_now()), "state": state,
               "text": text, "text_bn": text_bn}
        self.out.write(json.dumps(row, ensure_ascii=False) + "\n")
        self.out.flush()
        return row
