"""Run the stages of a pass side by side and still print them top to bottom."""
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor


class _PerStage:
    """stdout while stages run side by side: what a stage's thread prints is kept under that stage, the rest passes."""
    def __init__(self, real, count):
        self.real, self.parts, self.at = real, {n: [] for n in range(count)}, threading.local()

    def write(self, s):
        n = getattr(self.at, "stage", None)
        if n is None:
            return self.real.write(s)
        self.parts[n].append(s)
        return len(s)

    def flush(self):
        self.real.flush()

    def __getattr__(self, name):
        return getattr(self.real, name)


def run_stages(stages: list, jobs: int, first: int = 1, total: int = 0) -> list:
    """Run `(title, body)` stages, `jobs` at a time -> [clean, ...] in the order listed.

    Each prints under its `▶ [n/N]` heading, and the sections come out in the order listed whichever finishes first,
    so the pass reads the same every time. A body returns True when it ran clean. One that raises is reported as
    failed with the first line of its reason, and the others go on. With one job the stages run in this thread and
    print as they go."""
    total = total or len(stages)

    def work(n, title, body):
        print(("" if first + n == 1 else "\n") + f"▶ [{first + n}/{total}] {title}...")
        try:
            return bool(body())
        except (Exception, SystemExit) as exc:
            print(f"  ⚠️ {title} failed: {(str(exc) or type(exc).__name__).splitlines()[0]}")
            return False

    if jobs <= 1 or len(stages) <= 1:
        return [work(n, title, body) for n, (title, body) in enumerate(stages)]

    out = _PerStage(sys.stdout, len(stages))

    def threaded(n, title, body):
        out.at.stage, began = n, time.monotonic()
        clean = work(n, title, body)
        print(f"  … [{first + n}/{total}] {title}: {'done' if clean else 'needs a look'} in {time.monotonic() - began:.0f}s",
              file=sys.stderr, flush=True)
        return clean

    sys.stdout = out
    try:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = [pool.submit(threaded, n, title, body) for n, (title, body) in enumerate(stages)]
            results = []
            for n, future in enumerate(futures):         # in the order listed: a section waits for those before it
                results.append(future.result())
                out.real.write("".join(out.parts.pop(n)))
                out.real.flush()
    finally:
        sys.stdout = out.real
    return results
