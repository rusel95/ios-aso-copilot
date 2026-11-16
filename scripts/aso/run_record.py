"""What one collection pass leaves behind: a lock while it runs and a manifest when it ends.

`marketing/.lock` keeps a second pass out of the same store. `marketing/runs/<utc time>.json` says, per stage, how it
ended and how long it took, and, for the pass as a whole, which files it changed and how many rows each series gained.
Stages run side by side, so rows and files are the pass's, not one stage's."""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

SKIP = {".lock", "runs", "data", "public"}


class StoreLocked(RuntimeError):
    pass


def _state(store: Path) -> dict:
    """{relative path: (size, mtime_ns, rows)} for every file of the store a pass may write; rows only for csv."""
    found = {}
    for path in sorted(store.rglob("*")):
        rel = path.relative_to(store)
        if rel.parts[0] in SKIP or not path.is_file():
            continue
        stat = path.stat()
        rows = max(path.read_text(encoding="utf-8", errors="replace").count("\n") - 1, 0) if path.suffix == ".csv" else None
        found[rel.as_posix()] = (stat.st_size, stat.st_mtime_ns, rows)
    return found


class Run:
    """Hold the store's lock for the length of one pass and write its manifest at the end."""

    def __init__(self, store: Path, command: str):
        self.store, self.command = store, command
        self.started = datetime.now(timezone.utc)
        self.stages, self.order = {}, []
        self.lock = store / ".lock"
        self.before = {}

    def __enter__(self):
        try:
            fd = os.open(self.lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            held = self.lock.read_text(encoding="utf-8", errors="replace").strip()
            raise StoreLocked(f"{self.lock} exists ({held or 'no details'}): another pass is writing this store. "
                              "If none is running, check what it left, then remove the file.") from None
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(f"pid {os.getpid()} since {self.started:%Y-%m-%dT%H:%M:%SZ}")
        self.before = _state(self.store)
        return self

    def __exit__(self, kind, error, trace):
        try:
            self.write(crashed=error)
        finally:
            self.lock.unlink(missing_ok=True)
        return False

    def stages_of(self, stages: list) -> list:
        """The same `(title, body)` stages, each recording its status and duration when it runs."""
        self.order += [title for title, _ in stages]
        def recorded(title, body):
            def run():
                began = time.monotonic()
                status = "failed"
                try:
                    status = "clean" if (result := body()) else "needs a look"
                    return result
                finally:
                    self.stages[title] = {"status": status, "seconds": round(time.monotonic() - began, 1)}
            return run
        return [(title, recorded(title, body)) for title, body in stages]

    def write(self, crashed=None) -> Path:
        after = _state(self.store)
        touched = sorted(name for name in after if after[name][:2] != self.before.get(name, (None, None))[:2])
        rows = {name: after[name][2] - (self.before.get(name) or (0, 0, 0))[2]
                for name in touched if after[name][2] is not None}
        manifest = {"command": self.command, "started": f"{self.started:%Y-%m-%dT%H:%M:%SZ}",
                    "finished": f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ}",
                    "ended": "crashed" if crashed else "finished",
                    "stages": [{"stage": title, **info} for title, info in sorted(self.stages.items(), key=lambda kv: self.order.index(kv[0]))],
                    "files_touched": touched, "rows_added": {name: n for name, n in rows.items() if n}}
        folder = self.store / "runs"
        folder.mkdir(exist_ok=True)
        path = folder / f"{self.started:%Y%m%dT%H%M%SZ}.json"
        path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return path
