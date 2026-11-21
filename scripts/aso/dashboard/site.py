"""data files -> one self-contained page. Same data, same bytes: no network, no clock, nothing loaded from outside."""
from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path

from aso.dashboard.contract import ENTITIES, load_catalog, validate

ASSETS = Path(__file__).resolve().parents[3] / "assets" / "dashboard"
PLACEHOLDER = re.compile(r"\{\{(CSP|STYLE|PAYLOAD|SCRIPT)\}\}")


def digest(text: str) -> str:
    """The source expression a content security policy needs to allow exactly this inline text."""
    return "'sha256-" + base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode("ascii") + "'"


def read_data(data_dir: Path) -> tuple:
    """(relative path -> text, problems). Every period file found, and the three entity files, which must exist."""
    texts, problems = {}, []
    for kind in ("week", "snapshot"):
        for path in sorted((data_dir / kind).glob("*.json")):
            texts[f"{kind}/{path.name}"] = path.read_text(encoding="utf-8")
    for name in ENTITIES:
        if (data_dir / name).is_file():
            texts[name] = (data_dir / name).read_text(encoding="utf-8")
        else:
            problems.append((name, "the file is missing; run the export first"))
    return texts, problems


def page(texts: dict, catalog: dict, name: str) -> str:
    objects = {path: json.loads(text) for path, text in texts.items()}
    payload = {
        "name": name,
        "catalog": catalog,
        "places": json.loads((ASSETS / "places.json").read_text(encoding="utf-8")),
        "weeks": [objects[p] for p in sorted(objects) if p.startswith("week/")],
        "snapshots": [objects[p] for p in sorted(objects) if p.startswith("snapshot/")],
        "hypotheses": objects["hypotheses.json"],
        "keys": objects["keys.json"],
        "events": objects["events.json"],
        "notes": objects["notes.json"],
    }
    # compact, since nobody reads the page's source; `<` is escaped so no keyword can close the script element
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).replace("<", "\\u003c")
    style = (ASSETS / "style.css").read_text(encoding="utf-8")
    # the script is kept in parts, one per tab, and joined in the order of their names
    script = "\n".join(part.read_text(encoding="utf-8") for part in sorted((ASSETS / "js").glob("*.js")))
    policy = (f"default-src 'none'; style-src {digest(style)}; script-src {digest(script)}; "
              f"base-uri 'none'; form-action 'none'")
    parts = {"CSP": policy, "STYLE": style, "PAYLOAD": data, "SCRIPT": script}
    return PLACEHOLDER.sub(lambda m: parts[m.group(1)], (ASSETS / "template.html").read_text(encoding="utf-8"))


def build(data_dir: Path, out_dir: Path, name: str = "App") -> int:
    """Check every data file, then write `<out_dir>/index.html`. One bad file and nothing is written."""
    if not data_dir.is_dir():
        print(f"INVALID {data_dir}: no data folder; run the export first")
        print("FAIL data")
        return 1
    catalog = load_catalog()
    texts, problems = read_data(data_dir)
    problems += [(path, found) for path, text in texts.items() for found in validate(path, text, catalog)]
    for path, found in sorted(problems):
        print(f"INVALID {path}: {found}")
    if problems:
        print("FAIL data")
        return 1
    html = page(texts, catalog, name)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"PASS site ({len(texts)} files, {len(html.encode('utf-8'))} bytes)")
    return 0
