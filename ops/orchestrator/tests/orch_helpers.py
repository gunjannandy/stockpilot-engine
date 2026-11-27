"""Fixture builders for the dispatcher checks. Made-up data only."""
import sys
from pathlib import Path

ORCH = Path(__file__).resolve().parents[1]
if str(ORCH) not in sys.path:
    sys.path.insert(0, str(ORCH))

NOW = "2026-12-01T10:00:00+00:00"


def ago(minutes):
    from datetime import datetime, timedelta
    return (datetime.fromisoformat(NOW) - timedelta(minutes=minutes)).isoformat()


def ticket(number, key, owns=None, **kw):
    t = {"number": number, "key": key, "title": f"{key} title", "labels": ["ready-for-agent"],
         "blocked_by": [], "owns": ["area/%s/**" % key.lower()] if owns is None else owns,
         "unticked": [], "ui": False, "vm": False, "claims": [], "stuck_count": 0, "pr": None}
    t.update(kw)
    return t


def claim(account, at_minutes_ago, session=None):
    return {"account": account, "session": session or f"s-{account}", "at": ago(at_minutes_ago)}


def session(sid, key, account="secondary", status="working", last_event=1, connection="connected", **kw):
    s = {"id": sid, "account": account, "ticket": key, "kind": "builder", "status": status,
         "connection": connection, "last_event_at": ago(last_event), "nudged_at": None}
    s.update(kw)
    return s


OK5 = [{"window": "five_hour", "status": "allowed", "resetsAt": None}]


def world(tickets, sessions=None, account="secondary", quota=None, **kw):
    w = {"now": NOW, "account": account, "mode": "burst",
         "accounts": [{"name": "primary", "role": "driver", "weekly_reset": "Fri 22:30 IST"},
                      {"name": "secondary", "role": "spare", "weekly_reset": "Sun 18:30 IST"}],
         "tickets": tickets, "sessions": sessions or [],
         "quota": quota or {"primary": OK5, "secondary": OK5},
         "cloudflare": {"build_minutes": 0.1, "d1_writes": 0.1, "requests": 0.1, "actions_concurrency": 0.0},
         "private_runs": [], "trace": {"engine": "a\n", "private": "a\n", "open_pr": False},
         "left_over": [], "known_left_over": []}
    w.update(kw)
    return w


def keys(items, field="key"):
    return sorted(i[field] for i in items)
