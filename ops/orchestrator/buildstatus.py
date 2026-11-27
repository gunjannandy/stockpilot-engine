"""The build-status issue: one pinned issue, one comment per account, rewritten by that account's dispatcher."""
from datetime import datetime

import pace


def marker(account):
    return f"<!-- build-status:{account} -->"


def find_comment(comments, account):
    for c in comments:
        if c["body"].startswith(marker(account)):
            return c
    return None


def _ago(now, then):
    minutes = int((now - pace.parse_time(then)).total_seconds() // 60)
    return f"{minutes} min ago"


def render(account, now, readings, running, waiting, stuck):
    """running: [{key, number, session, pr, last_event_at}]; waiting: [keys]; stuck: [{key, session, action}]."""
    now = pace.parse_time(now)
    lines = [marker(account), f"### {account}", f"_Updated {now.isoformat(timespec='minutes')}_", ""]
    lines.append("**Quota**")
    if readings:
        for r in pace.latest(readings):
            lines.append(f"- {r['window']}: {r['status']}" + (f", resets {pace.parse_time(r['resetsAt']).isoformat(timespec='minutes')}"
                                                              if r.get("resetsAt") else ""))
    else:
        lines.append("- no reading yet")
    lines += ["", "**Running tickets**"]
    for r in running:
        pr = f"PR #{r['pr']}" if r.get("pr") else "no PR"
        beat = f"last heartbeat {_ago(now, r['last_event_at'])}" if r.get("last_event_at") else "no heartbeat"
        lines.append(f"- #{r['number']} {r['key']}: session {r['session'] or 'none'}, {pr}, {beat}")
    if not running:
        lines.append("- none")
    lines += ["", f"**Prototypes waiting** ({len(waiting)} of 3 on this account)"]
    lines += [f"- {k}" for k in waiting] or ["- none"]
    lines += ["", "**Stuck sessions**"]
    lines += [f"- {s['key']} ({s['session']}): {s['action']}" for s in stuck] or ["- none"]
    return "\n".join(lines) + "\n"
