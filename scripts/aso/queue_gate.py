"""The approval gate: an action that changes the outside world runs only against an entry of `queue.md`
whose exact command is the one about to run, and each entry runs once. Reads and appends inside the store only."""

import datetime as dt
import re
import shlex
from pathlib import Path


def queued_command(store: Path, queue_id: str):
    """The argv written on the **Command** line of queue entry `queue_id`, or None when there is no such entry."""
    queue = store / "queue.md"
    if not re.fullmatch(r"Q\d+", queue_id or "") or not queue.is_file():
        return None
    entry = None
    for line in queue.read_text(encoding="utf-8").splitlines():
        heading = re.match(r"###\s+(Q\d+)\b", line)
        if heading:
            entry = heading.group(1)
        elif entry == queue_id and line.startswith("**Command**:"):
            try:
                return shlex.split(line.split(":", 1)[1])
            except ValueError:
                return None
    return None


def executed(store: Path, queue_id: str) -> bool:
    log = store / "decisions.md"
    return log.is_file() and f"{queue_id} approved, executed" in log.read_text(encoding="utf-8")


def refusal(store: Path, queue_id, argv: list):
    """Why `argv` may not run now, or None when `queue_id` names an entry whose command is exactly `argv`."""
    if not queue_id:
        return "this action changes the outside world; pass --queue-id Qnnn naming an approved entry of queue.md"
    wanted = queued_command(store, queue_id)
    if wanted is None:
        return f"{queue_id} is not an entry of {store / 'queue.md'} with a **Command** line"
    if wanted != argv:
        return f"{queue_id} queues a different command than the one about to run: {shlex.join(wanted)}"
    if executed(store, queue_id):
        return f"{queue_id} was executed already (see decisions.md); queue a new entry to run it again"
    return None


def record_execution(store: Path, queue_id: str, effect: str, today: dt.date = None):
    """Append the executed approval to decisions.md. The queue entry itself stays."""
    day = (today or dt.date.today()).isoformat()
    with (store / "decisions.md").open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {day} — {queue_id} approved, executed\n**Evidence**: queue.md {queue_id}: {effect}\n"
                 f"**Supersedes**: none\n")
