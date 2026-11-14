"""Readers of the marketing store. Every command reads the store through these, so a file is parsed one way."""
from __future__ import annotations

import csv
import datetime as dt
import re
import sys
from pathlib import Path

RANK_HEADER = ["date", "market", "keyword", "group", "position", "popularity",
               "difficulty", "source", "depth", "status"]
# status vocabulary: ok = found at `position`; beyond-depth = queried, absent within `depth`;
# error = request failed; no-results = the API answered with ZERO results (some storefronts and scripts return
# nothing for a native query: si, bg, lt, lv, ee, md, Dravidian), so the query cannot say where we stand —
# it is not "beyond depth". A keyword never queried has no row at all — that is not the same thing.

# Every input this run could not use. A store file that cannot be parsed must never be skipped
# quietly: a dropped hypothesis reads exactly like a hypothesis that does not exist, and a ledger
# that hides its own blind spots is worse than no ledger.
PROBLEMS: list = []


def problem(where: str, why: str):
    PROBLEMS.append((where, why))


LABELS = {"**App ID**:": "app_id", "**Apple Ads profile**:": "profile", "**Apple Ads account**:": "account",
          "**Apple Ads genres**:": "genres", "**Apple Ads topic words**:": "topics"}


def read_config(store: Path) -> dict:
    cfg = {}
    path = store / "config.md"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            for label, key in LABELS.items():
                value = line[len(label):].strip() if line.startswith(label) else ""
                if value and not value.upper().startswith("TODO"):
                    cfg[key] = value
    cfg["app_id"] = (cfg.get("app_id") or "").split(maxsplit=1)[0] if cfg.get("app_id") else ""
    cfg["genres"] = [g.strip().upper() for g in cfg.get("genres", "").split(",") if g.strip()]
    cfg["topics"] = [t.strip().casefold() for t in cfg.get("topics", "").split(",") if t.strip()]
    return cfg


def norm(text) -> str:
    return " ".join((text or "").casefold().split())


def read_csv(path: Path) -> list:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def append_csv(path: Path, cols: list, rows: list) -> None:
    if not rows:
        return
    new = not path.is_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
        if new:
            writer.writeheader()
        writer.writerows(rows)


def read_ranks(store: Path):
    path = store / "metrics" / "ranks.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for i, r in enumerate(rows, 2):
        raw = (r.get("position") or "").strip()
        # Stores written before `status` existed use a word in this column ("absent", "not found")
        # to mean the same thing, and a hand-edited file can hold anything at all. Read what is
        # readable, flag what is not, and never let an unreadable value become a position.
        r["position"] = None
        if raw:
            try:
                value = int(raw)
            except ValueError:
                value = None
            if value is None:
                if raw.lower() not in ("absent", "not found", "none", "-"):
                    problem(f"metrics/ranks.csv:{i}", f"position {raw!r} is neither a number nor a "
                                                      f"known word for absent; read as not observed")
            elif value < 1:
                problem(f"metrics/ranks.csv:{i}", f"position {raw!r} is not a rank; read as not observed")
            else:
                r["position"] = value
        if not (r.get("market") or "").strip() or not (r.get("keyword") or "").strip():
            problem(f"metrics/ranks.csv:{i}", "row has no market or no keyword; it can never be paired")
        if not (r.get("status") or "").strip():
            r["status"] = "ok" if r["position"] is not None else ("beyond-depth" if raw else "unknown")
        r["depth"] = (r.get("depth") or "").strip()
        r["legacy"] = not r["depth"]
        # In the wild this column holds a whole sentence:
        # "itunes-search-api@2026-08-28 limit=182 hypothesis=H003". Comparability keys on the
        # provider; the rest of the string is a note, and matching it exactly would make every
        # pair incomparable for the sole reason that each observation described itself.
        r["provider"] = re.split(r"[@\s]", (r.get("source") or "").strip(), maxsplit=1)[0]
    return rows


def read_markets(store: Path):
    path = store / "metrics" / "markets.csv"
    out = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as fh:
        for i, r in enumerate(csv.DictReader(fh), 2):
            code, usd = (r.get("storefront") or "").strip().lower(), (r.get("proceeds_usd") or "").strip()
            if not code:
                continue                      # territory with no storefront code: expected, not a fault
            if not usd:
                problem(f"metrics/markets.csv:{i}", f"{code} has no proceeds_usd; it cannot be ranked by value")
                continue
            try:
                out[code] = float(usd)
            except ValueError:
                problem(f"metrics/markets.csv:{i}", f"{code} proceeds_usd {usd!r} is not a number")
    return out


def hyp_markets(h):
    return [m.strip().lower() for m in (h.get("markets") or "").split(",") if m.strip()]


def read_brand_tokens(store: Path):
    """Brand queries measure whether we are indexed, never demand. Nobody searches a brand they have
    not heard of, so a brand term is not an acquisition target and must not be ranked as one."""
    config = store / "config.md"
    if not config.exists():
        return []
    found = re.search(r"^\*\*Brand tokens\*\*:\s*(.+)$", config.read_text(encoding="utf-8"), re.M)
    return [b.strip().lower() for b in found.group(1).split(",") if b.strip()] if found else []


def read_hypotheses(store: Path, kinds=("H",)):
    """Hypothesis files as dicts of their frontmatter. `kinds` picks the id letters: H (store and in-app
    hypotheses, the default) and C (channel experiments, which carry no markets and no queries)."""
    out = []
    paths = sorted(p for kind in kinds for p in (store / "hypotheses").glob(f"{kind}[0-9]*.md"))
    for path in paths:
        text = path.read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---", text, re.S)
        if not match:
            problem(f"hypotheses/{path.name}", "no YAML frontmatter — NOT in the ledger at all, so it "
                                               "can never be judged, closed or counted")
            continue
        meta, key = {}, None
        for line in match.group(1).splitlines():
            field = re.match(r"^([a-z_]+):\s*(.*)$", line)
            if field:
                key = field.group(1)
                # frontmatter written from the template keeps its inline "# what this field means"
                value = re.sub(r"\s+#.*$", "", field.group(2)).strip().strip(">|").strip()
                meta[key] = value
            elif key and line.strip():
                meta[key] = (meta[key] + " " + line.strip()).strip()
        meta["_path"] = path.name
        if not (meta.get("id") or "").strip():
            problem(f"hypotheses/{path.name}", "frontmatter has no `id:` — NOT in the ledger")
            continue
        if meta["id"].startswith("C"):
            out.append(meta)                  # a channel experiment is not paired with rank observations
            continue
        if not (meta.get("markets") or "").strip():
            problem(f"hypotheses/{meta['id']}", "frontmatter has no `markets:`; rank exposure cannot be joined")
        if (meta.get("primary_signal") or "rank").strip() != "funnel" and not (meta.get("queries") or "").strip():
            problem(f"hypotheses/{meta['id']}", "rank hypothesis has no `queries:` basket; it cannot be judged")
        out.append(meta)
    seen = {}
    for h in out:
        seen.setdefault(h["id"], []).append(h["_path"])
    for hid, files in seen.items():
        if len(files) > 1:
            problem(f"hypotheses/{hid}", f"id claimed by {len(files)} files ({', '.join(files)}); "
                                         f"ids are never reused, so one of them is mislabelled")
    return out


def parse_date(value):
    try:
        return dt.date.fromisoformat((value or "").strip()[:10])
    except ValueError:
        return None


def demand_lookup(store: Path):
    """(heads, cuts) from the latest stored week per market.
    heads[(market, term)] = (popularity_100, week) for any stored head row; cuts[market] = (lowest listed score or None, week);
    a None score means Apple listed nothing for that storefront."""
    cut_rows = read_csv(store / "metrics" / "popularity_cut.csv")
    latest = {}
    for r in cut_rows:
        latest[r["market"]] = max(latest.get(r["market"], ""), r["week"])
    cuts = {}
    for market, week in latest.items():
        scores = [int(r["min_popularity_100"]) for r in cut_rows
                  if r["market"] == market and r["week"] == week and r["min_popularity_100"] != ""]
        cuts[market] = (min(scores) if scores else None, week)
    heads = {}
    for r in read_csv(store / "metrics" / "popularity.csv"):
        if r["week"] == latest.get(r["market"]):  # `why` records how the row was picked at pull time, not whether it is tracked now
            key = (r["market"], r["term"])
            heads[key] = (max(int(r["popularity_100"]), heads.get(key, (0, ""))[0]), r["week"])
    return heads, cuts


def print_problems(stream=sys.stdout):
    """Every command prints this, not just `report` — a command that finds a broken row and says
    nothing is the silent failure this whole section exists to prevent."""
    seen = list(dict.fromkeys(PROBLEMS))       # a refresh reads the store several times per run
    if not seen:
        if stream is sys.stdout:
            print("\n_Every store file parsed cleanly._")
        return
    print(f"\n## ⚠ {len(seen)} inputs this run could not use\n", file=stream)
    print("| Where | What went wrong |\n|---|---|", file=stream)
    for where, why in seen:
        print(f"| `{where}` | {why} |", file=stream)
    print("\nThese are not counted anywhere. Fix them or the ledger is answering a question "
          "about a smaller store than you have.", file=stream)
