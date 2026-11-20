"""The ledger's own self-check: run with `ledger.py --self-check`."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from aso.ledger_ingest import draft, ingest, ingest_by_observed_day, load_snapshot, refresh
from aso.ledger_report import section_a, section_b, section_c
from aso.ranks import brand_hit, movement, series, zero_result_keys
from aso.store import PROBLEMS, demand_lookup, read_brand_tokens, read_hypotheses, read_markets, read_ranks


def _empty_snapshot(store: Path) -> Path:
    path = store / "empty_results.json"
    path.write_text(json.dumps([{"country_code": "si", "term": "stiskanje videa", "our_rank": None,
                                 "total_results": "0", "query_status": "ok"}]), encoding="utf-8")
    return path


def self_check():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp)
        (store / "metrics").mkdir()
        (store / "hypotheses").mkdir()
        (store / "metrics" / "markets.csv").write_text(
            "territory,storefront,currency,customer_price,proceeds_local,fx_to_usd,proceeds_usd,source\n"
            "DEU,de,EUR,35.99,25.71,0.86,29.88,test\n", encoding="utf-8")
        snap = store / "s1.json"
        snap.write_text(json.dumps([
            {"country_code": "de", "term": "fotos komprimieren", "our_rank": 40, "total_results": 200},
            {"country_code": "de", "term": "video komprimieren", "our_rank": None, "total_results": 200},
            {"country_code": "de", "term": "stale", "our_rank": 12, "total_results": 5},   # impossible
            {"country_code": "de", "term": "failed", "our_rank": None, "query_status": "error"},
        ]), encoding="utf-8")
        assert ingest(store, snap, "2026-09-01", "itunes-search-api", 200, "target") == 3, "stale row must be refused"
        failed = [r for r in read_ranks(store) if r["keyword"] == "failed"]
        assert failed and failed[0]["status"] == "error", "a failed request is not beyond-depth"
        empty_rows, _ = load_snapshot(_empty_snapshot(store))
        assert empty_rows[0][3] == "no-results", "an empty result list is not 'beyond depth'"
        snap2 = store / "s2.json"
        snap2.write_text(json.dumps([
            {"country_code": "de", "term": "fotos komprimieren", "our_rank": 8, "total_results": 200},
            {"country_code": "de", "term": "video komprimieren", "our_rank": 30, "total_results": 200},
        ]), encoding="utf-8")
        ingest(store, snap2, "2026-09-08", "itunes-search-api", 200, "target")
        assert ingest(store, snap2, "2026-09-08", "itunes-search-api", 200, "target") == 0, "must dedupe"
        aside = store / "aside"                # its own store: fixtures must not perturb the rest
        (aside / "metrics").mkdir(parents=True)
        twice = aside / "twice.json"
        twice.write_text(json.dumps([
            {"country_code": "de", "term": "dup", "our_rank": None, "total_results": 200},
            {"country_code": "de", "term": "dup", "our_rank": None, "total_results": 200},
        ]), encoding="utf-8")
        assert ingest(aside, twice, "2026-09-08", "itunes-search-api", 200, "target") == 1, \
            "a snapshot listing one query twice must write one row"
        pairs = series(read_ranks(store))
        assert movement(*[pairs[("de", "fotos komprimieren")][i] for i in (0, -1)]) == ("improved", 32)
        label, delta = movement(*[pairs[("de", "video komprimieren")][i] for i in (0, -1)])
        assert delta is None and label.startswith("ENTERED"), "censored → number is not a delta"
        single = series(read_ranks(store))[("de", "fotos komprimieren")][:1]
        assert movement(single[0], single[0]) == ("only one observation date", None), \
            "one observation is not a flat pair"
        bad = store / "metrics" / "bad.csv"
        bad.write_text("date,market,keyword,group,position,popularity,difficulty,source,depth,status\n"
                       "2026-09-01,de,x,target,--5,,,itunes-search-api,200,ok\n"
                       "2026-09-02,de,y,target,-5,,,itunes-search-api,200,ok\n", encoding="utf-8")
        keep_ranks = (store / "metrics" / "ranks.csv").read_text(encoding="utf-8")
        (store / "metrics" / "ranks.csv").write_text(bad.read_text(encoding="utf-8"), encoding="utf-8")
        PROBLEMS.clear()
        rows = read_ranks(store)               # must not raise on a hand-edited position
        assert all(r["position"] is None for r in rows), "a non-rank must not band as top3"
        assert len(PROBLEMS) == 2, PROBLEMS     # one unreadable value, one non-rank
        PROBLEMS.clear()
        (store / "metrics" / "ranks.csv").write_text(keep_ranks, encoding="utf-8")
        legacy = store / "metrics" / "legacy.csv"
        legacy.write_text("date,market,keyword,group,position,popularity,difficulty,source\n"
            "2026-08-23,de,weisses rauschen,target,43,,,itunes-search-api@2026-08-23 limit=200 baseline\n"
            "2026-09-04,de,weisses rauschen,target,21,,,itunes-search-api@2026-09-04 limit=182 H003\n",
            encoding="utf-8")
        import shutil
        keep = (store / "metrics" / "ranks.csv").read_text(encoding="utf-8")
        shutil.copy(legacy, store / "metrics" / "ranks.csv")
        lrows = series(read_ranks(store))[("de", "weisses rauschen")]
        assert movement(lrows[0], lrows[-1]) == ("improved · legacy, depth not recorded", 22), \
            "a store that writes its provenance as prose must still pair"
        (store / "metrics" / "ranks.csv").write_text(keep, encoding="utf-8")
        (store / "hypotheses" / "H001-x.md").write_text(
            "---\nid: H001\nmarkets: de\nqueries: fotos komprimieren\nwent_live: 2026-08-01\nwindow_days: 21\nverdict:\n---\n", encoding="utf-8")
        (store / "hypotheses" / "H002-x.md").write_text(
            "---\nid: H002\nwent_live:\nwindow_days: 21\nverdict:\n---\n", encoding="utf-8")
        PROBLEMS.clear()
        hyps = read_hypotheses(store)
        assert [h["id"] for h in hyps] == ["H001", "H002"]
        messages = " ".join(message for _, message in PROBLEMS)
        assert "no `markets:`" in messages and "no `queries:`" in messages, \
            "legacy hypotheses must be reported as malformed"
        PROBLEMS.clear()
        by_market = {"de": [obs for (m, _), obs in pairs.items() if m == "de"]}
        counts = section_a(hyps, by_market, read_markets(store))
        assert counts["due"] == 1 and counts["not-shipped"] == 1, counts
        (store / "config.md").write_text("**Brand tokens**: komprimieren\n", encoding="utf-8")
        assert read_brand_tokens(store) == ["komprimieren"]
        assert not section_c(pairs, read_markets(store), hyps, 10, ["komprimieren"]), \
            "a brand term is not an acquisition target"
        assert brand_hit("pixel", "pixel: resize photos") and brand_hit("pixel", "Pixel")
        assert brand_hit("pixel", "pixel写真圧縮") and not brand_hit("pixel", "pixelator"), \
            "a generic query that contains the brand's letters is not a brand query"
        scored = section_c(pairs, read_markets(store), hyps, 10, [])
        assert scored and scored[0][1] == "de" and scored[0][5] == 29.88
        assert scored[0][2] == "video komprimieren" and scored[-1][2] == "fotos komprimieren", (
            "a #30 with room must outrank a #8 that is nearly top3")
        assert all(s[0] > 0 for s in scored), "score must use real proceeds, never a stored opportunity field"
        import io, contextlib
        with contextlib.redirect_stdout(io.StringIO()) as plain:
            section_c(pairs, read_markets(store), hyps, 10, [], demand_lookup(store))
        assert "Demand" not in plain.getvalue(), "no radar data, no Demand column"
        with contextlib.redirect_stdout(io.StringIO()) as b_brand:
            section_b(pairs, read_markets(store), 10, ["komprimieren"])
        assert "brand-term keys excluded" in b_brand.getvalue() and "| de |" not in b_brand.getvalue(), \
            "section B must drop brand-token keys and say how many it dropped"
        with contextlib.redirect_stdout(io.StringIO()) as b_plain:
            section_b(pairs, read_markets(store), 10, [])
        assert "| de |" in b_plain.getvalue(), "without brand tokens section B keeps the keys"
        (store / "metrics" / "popularity_cut.csv").write_text(
            "week,captured,market,genre,listed,min_popularity_100,source\n"
            "2026-09-20,2026-09-29,de,PHOTO_VIDEO,300,45,test\n", encoding="utf-8")
        (store / "metrics" / "popularity.csv").write_text(
            "week,captured,market,genre,term,rank_in_genre,popularity_100,popularity_5,why,source\n"
            "2026-09-20,2026-09-29,de,PHOTO_VIDEO,video komprimieren,185,55,3,basket,test\n", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()) as with_demand:
            section_c(pairs, read_markets(store), hyps, 10, [], demand_lookup(store))
        table = with_demand.getvalue()
        assert "| video komprimieren | head 55 |" in table and "| fotos komprimieren | below 45 |" in table, table
        (store / "metrics" / "popularity_cut.csv").unlink()
        (store / "metrics" / "popularity.csv").unlink()
        (store / "config.md").write_text("**Brand tokens**: pixel\n", encoding="utf-8")
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            hid = draft(store, "de", ["fotos komprimieren"], 21, None)
        body = buf.getvalue()
        assert hid == "H003", hid
        assert "queries: fotos komprimieren" in body and "kill_criterion_written:" in body
        assert "not better than 8" in body, "kill criterion must carry the real baseline"
        assert "In flight in this storefront" in body, "must warn about a concurrent experiment"
        for bad in ("never queried", "failed"):   # "failed" exists but only as a failed request
            try:
                draft(store, "de", [bad], 21, None)
                raise AssertionError(f"must refuse a basket it cannot measure: {bad}")
            except SystemExit as exc:
                assert "no successful observation" in str(exc), exc

        (store / "config.md").write_text("**Brand tokens**: pixel\n", encoding="utf-8")
        try:
            draft(store, "de", ["pixel: fotos komprimieren"], 21, None)
            raise AssertionError("draft must refuse brand queries")
        except SystemExit as exc:
            assert "contains brand token(s)" in str(exc), exc

        try:
            refresh(store, "test.bundle", [], False, 1.0, store / "snapshots")
            raise AssertionError("refresh must refuse delays below its local minimum")
        except SystemExit as exc:
            assert "--delay must be at least 3.0 seconds" in str(exc), exc

        # per-market ingest dates each entry by its own observed_at, not by the run's start day
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            n = ingest_by_observed_day(store, {"de": [
                {"term": "split day", "country": "de", "our_rank": 4, "total_results": 50, "query_status": "ok",
                 "observed_at": "2031-05-01T20:59:00+00:00"},
                {"term": "split day 2", "country": "de", "our_rank": 5, "total_results": 50, "query_status": "ok",
                 "observed_at": "2031-05-04T10:00:00+00:00"}]})
        assert n == 2
        days = {r["date"] for r in read_ranks(store) if r["keyword"].startswith("split day")}
        assert len(days) == 2 and "2031-05-04" in days, days
        # a key whose latest reading is an empty list is unmeasurable; once it answers again it is measurable
        # and a single empty answer does not erase older legitimate history
        def row(date, status, pos=None):
            return {"date": date, "market": "si", "keyword": "stiskanje videa", "status": status, "position": pos}
        assert zero_result_keys([row("2031-01-01", "beyond-depth"), row("2031-01-02", "no-results")]) == \
            {("si", "stiskanje videa")}
        assert zero_result_keys([row("2031-01-01", "no-results"), row("2031-01-02", "beyond-depth")]) == set()
        assert zero_result_keys([row("2031-01-01", "ok", 5), row("2031-01-02", "no-results"),
                                 row("2031-01-03", "ok", 6)]) == set()
        kept = series([row("2031-01-01", "no-results"), row("2031-01-02", "beyond-depth")])
        assert [r["date"] for r in kept[("si", "stiskanje videa")]] == ["2031-01-02"], "an empty answer is no observation"
        with contextlib.redirect_stdout(io.StringIO()):
            ingest_by_observed_day(store, {"de": [{"term": "carry group", "country": "de", "our_rank": 9,
                                                   "total_results": 50, "query_status": "ok",
                                                   "observed_at": "2031-06-01T10:00:00+00:00"}]},
                                   groups={("de", "carry group"): "asa-observed"})
        assert [r["group"] for r in read_ranks(store) if r["keyword"] == "carry group"] == ["asa-observed"]
        from unittest.mock import patch
        import ledger
        if True:
            with patch.object(sys, "argv", ["ledger.py", "--store", str(store), "report",
                                             "--as-of", "2025-01-02"]):
                with contextlib.redirect_stdout(io.StringIO()) as report_output:
                    ledger.main()
            assert "# Marketing ledger · 2025-01-02" in report_output.getvalue()
            with patch.object(sys, "argv", ["ledger.py", "--store", str(store), "refresh",
                                             "--bundle", "test.bundle", "--as-of", "2025-01-02"]):
                with contextlib.redirect_stderr(io.StringIO()):
                    try:
                        ledger.main()
                        raise AssertionError("refresh must reject --as-of before any network call")
                    except SystemExit as exc:
                        assert exc.code == 2
    print("\nOK: stale positions, failed requests, dedupe, one-observation keys, unreadable positions,\n"
          "    censored pairs, legacy provenance/schema warnings, date replay, delay guard,\n"
          "    window states, proceeds-weighted order, per-observation ingest dates")
