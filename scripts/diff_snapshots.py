#!/usr/bin/env python3
"""
diff_snapshots.py — Compare two ASO rank audit snapshots across all markets.

Usage:
    python3 marketing/scripts/diff_snapshots.py <file1.json|md> <file2.json|md>
"""

import sys, json, re
from pathlib import Path

FLAGS = {
    "us":"🇺🇸","gb":"🇬🇧","de":"🇩🇪","fr":"🇫🇷","jp":"🇯🇵","kr":"🇰🇷",
    "cn":"🇨🇳","tw":"🇹🇼","br":"🇧🇷","ru":"🇷🇺","ua":"🇺🇦","es":"🇪🇸",
    "mx":"🇲🇽","it":"🇮🇹","pl":"🇵🇱","nl":"🇳🇱","se":"🇸🇪","tr":"🇹🇷",
    "in":"🇮🇳","sa":"🇸🇦","il":"🇮🇱","au":"🇦🇺","ca":"🇨🇦","sg":"🇸🇬",
    "hk":"🇭🇰",
}

def load_data(path_str: str) -> dict:
    p = Path(path_str)
    if not p.exists():
        print(f"Error: {path_str} does not exist", file=sys.stderr)
        sys.exit(1)
        
    if p.suffix == ".json":
        return json.loads(p.read_text())
        
    # If markdown, parse tables
    text = p.read_text()
    markets = {}
    sections = re.split(r"\n###\s+(?:[^\n]+)\s+([A-Z]{2})\s+[·-]\s+", text)
    for i in range(1, len(sections), 2):
        country = sections[i].lower()
        sec_text = sections[i+1]
        ranked = []
        if "Ranked (top-200):" in sec_text:
            part = sec_text.split("Ranked (top-200):")[1]
            if "Not ranked" in part:
                part = part.split("Not ranked")[0]
            for line in part.strip().split("\n"):
                if not line.startswith("|") or "Rank" in line or "---" in line:
                    continue
                cells = [c.strip() for c in line.split("|")[1:-1]]
                if len(cells) >= 2:
                    r_str = cells[0].replace("#", "").strip()
                    kw = cells[1].strip("` ")
                    try:
                        r = int(r_str)
                        ranked.append({"term": kw, "our_rank": r})
                    except ValueError:
                        continue
        markets[country] = ranked
    return markets

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 diff_snapshots.py <before.json|md> <after.json|md>")
        sys.exit(1)
        
    p1, p2 = sys.argv[1], sys.argv[2]
    d1, d2 = load_data(p1), load_data(p2)
    
    all_markets = sorted(set(list(d1.keys()) + list(d2.keys())))
    
    print(f"\n# ASO Rank Audit Snapshot Diff: {Path(p1).name} → {Path(p2).name}\n")
    print(f"| Ринок | Було ранжовано | Стало | Δ к-сть | Найкращий було | Найкращий стало | Статус |")
    print("|---|---|---|---|---|---|---|")
    
    market_details = {}
    
    for m in all_markets:
        flag = FLAGS.get(m, "🌐")
        r1 = {x["term"]: x.get("our_rank") for x in d1.get(m, []) if x.get("our_rank")}
        r2 = {x["term"]: x.get("our_rank") for x in d2.get(m, []) if x.get("our_rank")}
        
        c1, c2 = len(r1), len(r2)
        diff_count = c2 - c1
        diff_str = f"+{diff_count}" if diff_count > 0 else str(diff_count)
        
        best1 = min(r1.values()) if r1 else None
        best2 = min(r2.values()) if r2 else None
        
        b1_str = f"#{best1}" if best1 else "—"
        b2_str = f"#{best2}" if best2 else "—"
        
        status = "—"
        if diff_count > 0 or (best2 and best1 and best2 < best1):
            status = "🟢 Ріст"
        elif diff_count < 0 or (best2 and best1 and best2 > best1):
            status = "🔴 Спад"
        elif c2 > 0:
            status = "🟡 Стабільно"
            
        print(f"| {flag} {m.upper()} | {c1} | {c2} | {diff_str} | {b1_str} | {b2_str} | {status} |")
        
        # Details
        new_kws = [k for k in r2 if k not in r1]
        improved = [k for k in r2 if k in r1 and r2[k] < r1[k]]
        dropped = [k for k in r2 if k in r1 and r2[k] > r1[k]]
        lost = [k for k in r1 if k not in r2]
        
        if new_kws or improved or dropped or lost:
            market_details[m] = {
                "new": [(k, r2[k]) for k in new_kws],
                "improved": [(k, r1[k], r2[k]) for k in improved],
                "dropped": [(k, r1[k], r2[k]) for k in dropped],
                "lost": [(k, r1[k]) for k in lost],
            }
            
    print("\n## Деталі по ключових змінах\n")
    for m, det in market_details.items():
        flag = FLAGS.get(m, "🌐")
        print(f"### {flag} {m.upper()}")
        for kw, r in det["new"]:
            print(f"- 🟢 **Новий у видачі**: `{kw}` → #{r}")
        for kw, r_old, r_new in det["improved"]:
            print(f"- ⬆️ **Підйом**: `{kw}`: #{r_old} → #{r_new} (↑{r_old - r_new})")
        for kw, r_old, r_new in det["dropped"]:
            print(f"- ⬇️ **Просідання**: `{kw}`: #{r_old} → #{r_new} (↓{r_new - r_old})")
        for kw, r_old in det["lost"]:
            print(f"- 🔴 **Випав з топ-200**: `{kw}` (був #{r_old})")
        print()

if __name__ == "__main__":
    main()
