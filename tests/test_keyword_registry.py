"""The keyword registry: one pool, one logical row per (market, query), with where each keyword came from.

Every test works on a copy of the sample store with a few extra files; nothing here reaches the network, and nothing
writes under assets/sample/store.
"""
import ast
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.helpers import AS_OF, ROOT, copy_store, run  # noqa: E402

from aso import keyword_registry as kr  # noqa: E402
from aso.ranks import key_of  # noqa: E402

RANK_HEAD = "date,market,keyword,group,position,popularity,difficulty,source,depth,status\n"


def write(store: Path, relative: str, text: str) -> Path:
    path = store / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def append(store: Path, relative: str, text: str) -> None:
    with (store / relative).open("a", encoding="utf-8") as fh:
        fh.write(text)


def built(store: Path, as_of: str = AS_OF) -> dict:
    """The registry's latest row per key, after one build."""
    kr.build(store, as_of)
    return {(r["market"], r["key_norm"]): r for r in kr.read_registry(store)}


class Normalization(unittest.TestCase):
    def test_case_spacing_and_composed_letters_fold(self):
        self.assertEqual(kr.key_norm("  Tide   TRACKER "), "tide tracker")
        self.assertEqual(kr.key_norm("café"), kr.key_norm("café"))          # NFC: two ways to type é are one

    def test_the_two_apostrophes_are_two_queries(self):
        ascii_, typographic = "пам'ять", "пам’ять"
        self.assertNotEqual(kr.key_norm(ascii_), kr.key_norm(typographic))
        # The comparison is the rank ledger's loose form, and it is made at read time, never written into the file.
        self.assertEqual(key_of("ua", ascii_), key_of("ua", typographic))


class Build(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = copy_store(self._tmp.name)

    def test_one_row_a_key_from_every_source(self):
        write(self.store, "keywords/tracking-us.txt",
              "# Tidepool tracking\n## TARGET (2)\n  Tide   TRACKER \n  Wave   Height \n")
        write(self.store, "ads/us_reviewed/accepted.csv",
              "text,language,evidence\ntide tracker,en,model\nwave height,en,model\ntide chart,en,search_term\n")
        rows = built(self.store)
        shared = rows[("us", "tide tracker")]
        self.assertEqual(shared["keyword"], "tide tracker")                      # the first spelling stands: ranks read it first
        self.assertEqual(shared["sources"], "ads-keyword;hypothesis-basket;ranks;tracking-file")
        self.assertEqual((shared["tracked"], shared["hypotheses"]), ("yes", "H001"))
        self.assertEqual((shared["position"], shared["status"], shared["rank_date"]), ("7", "ok", "2026-11-09"))
        self.assertEqual((shared["first_seen"], shared["last_seen"]), ("2026-10-05", "2026-11-09"))
        only_file = rows[("us", "wave height")]
        self.assertEqual((only_file["keyword"], only_file["sources"], only_file["tracked"]), ("Wave Height", "ads-keyword;tracking-file", "no"))
        self.assertEqual(rows[("us", "tide chart")]["sources"], "ads-search-term")
        text = (self.store / kr.REGISTRY).read_text(encoding="utf-8").splitlines()
        filed = [r for r in csv.DictReader(text) if r["key_norm"] == "tide tracker"]
        self.assertEqual(len(filed), 1)                                           # one row, not one a source

    def test_the_sample_store_alone_gives_its_tracked_keys(self):
        rows = built(self.store)
        self.assertEqual(sorted(k for k in rows if rows[k]["tracked"] == "yes"),
                         sorted({(m, kr.key_norm(w)) for m, w in [
                             ("us", "tide tracker"), ("us", "tide times"), ("us", "surf forecast"),
                             ("us", "moon phase"), ("us", "sea level"), ("ua", "приплив"),
                             ("ua", "графік припливів"), ("ua", "прогноз хвиль"), ("ua", "фаза місяця"), ("ua", "п’ятниця море")]}))
        self.assertEqual(len(rows), 10)                       # the sample's brand word, tidepool, is tracked in us and ua: refused

    def test_the_two_apostrophes_stay_two_rows_and_the_hypothesis_names_one(self):
        append(self.store, "metrics/ranks.csv",
               "2026-11-09,ua,п'ятниця море,target,37,,,itunes-search-api,200,ok\n"
               "2026-11-09,ua,п’ятниця море,target,18,,,itunes-search-api,200,ok\n")
        write(self.store, "hypotheses/H008-ua-apostrophe.md",
              "---\nid: H008\nmarkets: ua\nqueries: п'ятниця море\nstatus: draft\n---\n")
        rows = built(self.store)
        plain, typographic = rows[("ua", "п'ятниця море")], rows[("ua", "п’ятниця море")]
        self.assertEqual((plain["position"], typographic["position"]), ("37", "18"))
        self.assertEqual((plain["hypotheses"], typographic["hypotheses"]), ("H008", ""))   # exact spelling, not the loose one
        found = kr.twins(list(rows.values()))
        self.assertEqual(found, [("ua", ["п'ятниця море", "п’ятниця море"])])

    def test_a_second_build_writes_nothing_and_a_later_day_too(self):
        write(self.store, "ads/us_reviewed/accepted.csv", "text,evidence\nwave height,model\n")
        first = kr.build(self.store, AS_OF)
        self.assertGreater(first["appended"], 0)
        before = (self.store / kr.REGISTRY).read_bytes()
        self.assertEqual(kr.build(self.store, AS_OF)["appended"], 0)
        self.assertEqual(kr.build(self.store, "2026-12-01")["appended"], 0)         # nothing new is not a new day's rows
        self.assertEqual((self.store / kr.REGISTRY).read_bytes(), before)

    def test_a_new_sweep_is_a_new_row_for_the_keys_it_changed_and_history_stays(self):
        built(self.store)
        before = (self.store / kr.REGISTRY).read_text(encoding="utf-8")
        append(self.store, "metrics/ranks.csv", "2026-11-16,us,tide tracker,target,5,,,itunes-search-api,200,ok\n")
        result = kr.build(self.store, "2026-11-16")
        self.assertEqual(result["appended"], 1)
        after = (self.store / kr.REGISTRY).read_text(encoding="utf-8")
        self.assertTrue(after.startswith(before))                                 # append-only: the old row is untouched
        latest = {(r["market"], r["key_norm"]): r for r in kr.read_registry(self.store)}[("us", "tide tracker")]
        self.assertEqual((latest["position"], latest["rank_date"], latest["last_seen"]), ("5", "2026-11-16", "2026-11-16"))

    def test_the_latest_good_read_stands_over_a_later_failed_one(self):
        append(self.store, "metrics/ranks.csv", "2026-11-16,us,moon phase,target,,,,itunes-search-api,200,error\n")
        row = built(self.store)[("us", "moon phase")]
        self.assertEqual((row["position"], row["status"], row["rank_date"]), ("30", "ok", "2026-11-09"))
        append(self.store, "metrics/ranks.csv", "2026-11-16,us,brand new,target,,,,itunes-search-api,200,error\n")
        failed = built(self.store)[("us", "brand new")]
        self.assertEqual((failed["position"], failed["status"], failed["tracked"]), ("", "error", "yes"))

    def test_popularity_below_the_cut_is_unknown_not_zero(self):
        write(self.store, "keywords/tracking-gb.txt", "storage\n")
        rows = built(self.store)
        self.assertEqual(rows[("us", "tide times")]["popularity"], "head 41")
        self.assertEqual(rows[("us", "tide tracker")]["popularity"], "below 38")
        self.assertEqual(rows[("ua", "приплив")]["popularity"], "no data")        # Apple lists nothing for ua
        self.assertEqual(rows[("gb", "storage")]["popularity"], "")                 # gb was never pulled: no answer at all

    def test_brand_keys_are_refused_from_every_source_and_own_metadata_is_flagged(self):
        write(self.store, "keywords/tracking-us.txt", "## OWN (1)\ntide\n## TARGET (2)\nsurf spots\ntidepool tracker\n")
        write(self.store, "ads/us_reviewed/accepted.csv", "text,evidence\ntidepool app,model\ntidepoolish,model\ntide pool,model\n")
        write(self.store, "hypotheses/H009-brand.md", "---\nid: H009\nmarkets: us\nqueries: tidepool;wave height\nstatus: draft\n---\n")
        append(self.store, "metrics/ranks.csv", "2026-11-09,us,my subtitle words,title,12,,,itunes-search-api,200,ok\n")
        result = kr.build(self.store, AS_OF)
        rows = {(r["market"], r["key_norm"]): r for r in kr.read_registry(self.store)}
        for brand in [("us", "tidepool"), ("ua", "tidepool"), ("us", "tidepool app"), ("us", "tidepool tracker")]:
            self.assertNotIn(brand, rows)                                           # ranks, ads, tracking list and basket alike
        self.assertEqual(result["refused"], [("ua", "tidepool"), ("us", "tidepool"), ("us", "tidepool app"), ("us", "tidepool tracker")])
        self.assertIn("tidepool", (self.store / "metrics" / "ranks.csv").read_text(encoding="utf-8"))   # the ledger is not touched
        self.assertEqual(rows[("us", "tidepoolish")]["excluded"], "")             # a brand token is a whole word, as everywhere
        self.assertIn(("us", "tide pool"), rows)                                    # only its letters, not the word: kept
        self.assertEqual(rows[("us", "tide")]["excluded"], "own-metadata")
        self.assertEqual(rows[("us", "my subtitle words")]["excluded"], "own-metadata")
        self.assertEqual(rows[("us", "surf spots")]["excluded"], "")
        self.assertEqual(rows[("us", "wave height")]["hypotheses"], "H009")         # the basket's other query still counts
        shown = kr.summary(list(rows.values()))
        self.assertEqual(shown["excluded"], {"own-metadata": 2})
        names = {c["keyword"] for c in shown["candidates"]}
        self.assertNotIn("tide", names)
        self.assertIn("surf spots", names)

    def test_an_older_registry_that_holds_brand_keys_is_cleaned_and_the_rest_is_left_as_it_was(self):
        kr.build(self.store, AS_OF)
        clean = (self.store / kr.REGISTRY).read_bytes()
        stale = ",".join(["us", "Tidepool", "tidepool", AS_OF, AS_OF, "ranks", "yes", "", "1", "ok", AS_OF, "", "brand", AS_OF])
        append(self.store, kr.REGISTRY, stale + "\n" + stale.replace("ranks", "ads-keyword") + "\n")
        self.assertNotIn(("us", "tidepool"), {(r["market"], r["key_norm"]) for r in kr.read_registry(self.store)})   # a reader never sees it
        result = kr.build(self.store, AS_OF)
        self.assertEqual((result["dropped"], result["appended"]), (1, 0))           # one key, though it held two rows
        self.assertEqual((self.store / kr.REGISTRY).read_bytes(), clean)
        self.assertEqual(kr.build(self.store, AS_OF)["dropped"], 0)

    def test_files_that_name_no_storefront_are_reported_not_dropped_quietly(self):
        write(self.store, "ads/de_reviewed/accepted.csv", "text,evidence\nvideo komprimieren,model\n")
        write(self.store, "ads/twhk_reviewed/accepted.csv", "text,evidence\n影片壓縮,model\n")
        write(self.store, "ads/reviewed_2026-10-02/reviewed_live.csv",
              "market,text,evidence\nua,стиснути відео,seed\ntwhk,照片壓縮,seed\n")
        write(self.store, "ads/nordic_h077/se/evidence/hints.tsv", "seed\trank\tsuggestion\nkomprimera\t1\tkomprimera video\n")
        write(self.store, "ads/de_candidates.csv", "text,evidence\nunreviewed phrase,model\n")       # before review: not a candidate yet
        write(self.store, "ads/de_reviewed/rejected.csv", "text,evidence\nrejected phrase,model\n")
        result = kr.build(self.store, AS_OF)
        rows = {(r["market"], r["key_norm"]): r for r in kr.read_registry(self.store)}
        self.assertEqual(rows[("de", "video komprimieren")]["sources"], "ads-keyword")
        self.assertEqual(rows[("ua", "стиснути відео")]["sources"], "ads-keyword")
        self.assertEqual(rows[("se", "komprimera video")]["sources"], "autocomplete-hints")
        self.assertNotIn("影片壓縮", " ".join(k[1] for k in rows))
        self.assertNotIn(("de", "unreviewed phrase"), rows)
        self.assertNotIn(("de", "rejected phrase"), rows)
        said = " ".join(f"{where}: {why}" for where, why in result["skipped"])
        self.assertIn("ads/twhk_reviewed/accepted.csv", said)
        self.assertIn("twhk", said)                                                 # the unplaced row of a placed file too


class Add(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = copy_store(self._tmp.name)

    def test_a_found_keyword_is_recorded_with_its_source_and_day(self):
        kr.build(self.store, AS_OF)                                # `add` folds the whole store too: start from a built one
        result = kr.add(self.store, "us", ["Tide Chart App", "tide times"], "autocomplete-hints", AS_OF)
        self.assertEqual(result["appended"], 2)                    # a new key, and tide times gains a source
        rows = {(r["market"], r["key_norm"]): r for r in kr.read_registry(self.store)}
        new = rows[("us", "tide chart app")]
        self.assertEqual((new["keyword"], new["sources"], new["tracked"]), ("Tide Chart App", "autocomplete-hints", "no"))
        self.assertEqual((new["first_seen"], new["last_seen"]), (AS_OF, AS_OF))
        self.assertEqual(rows[("us", "tide times")]["sources"], "autocomplete-hints;hypothesis-basket;popularity-head;ranks")
        self.assertEqual(kr.add(self.store, "us", ["Tide Chart App"], "autocomplete-hints", AS_OF)["appended"], 0)

    def test_a_brand_keyword_is_refused_and_a_generic_one_with_its_letters_is_kept(self):
        kr.build(self.store, AS_OF)
        result = kr.add(self.store, "us", ["Tidepool Tides", "tidepoolish", "tide pool", "wave height"], "google-suggest", AS_OF)
        self.assertEqual(result["refused"], [("us", "Tidepool Tides")])            # what was handed in, not the store's own brand keys
        self.assertEqual(result["appended"], 3)
        rows = {(r["market"], r["key_norm"]): r for r in kr.read_registry(self.store)}
        self.assertNotIn(("us", "tidepool tides"), rows)
        self.assertEqual(rows[("us", "tidepoolish")]["sources"], "google-suggest")
        self.assertIn(("us", "tide pool"), rows)
        self.assertNotIn("Tidepool Tides", (self.store / kr.REGISTRY).read_text(encoding="utf-8"))

    def test_a_source_outside_the_list_is_refused(self):
        with self.assertRaises(ValueError):
            kr.add(self.store, "us", ["x"], "a-friend-said", AS_OF)
        with self.assertRaises(ValueError):
            kr.add(self.store, "zz", ["x"], "google-suggest", AS_OF)          # not a storefront
        self.assertFalse((self.store / kr.REGISTRY).exists())


class Show(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = copy_store(self._tmp.name)

    def test_counts_candidates_overlaps_and_twins(self):
        write(self.store, "keywords/tracking-us.txt", "tide tracker\nwave height\n")
        write(self.store, "ads/us_reviewed/accepted.csv", "text,evidence\nwave height,model\ntide chart,model\n")
        append(self.store, "metrics/ranks.csv", "2026-11-09,ua,a'b,target,3,,,itunes-search-api,200,ok\n"
                                                "2026-11-09,ua,a’b,target,4,,,itunes-search-api,200,ok\n")
        rows = built(self.store)
        shown = kr.summary(list(rows.values()))
        self.assertEqual(shown["keys"], len(rows))
        self.assertEqual(shown["by_market"]["us"], {"keys": 7, "tracked": 5, "candidates": 2, "excluded": 0})
        self.assertEqual(shown["by_source"]["tracking-file"], 2)
        self.assertEqual(shown["by_source"]["ranks"], 12)
        self.assertEqual({c["keyword"] for c in shown["candidates"]}, {"wave height", "tide chart"})
        self.assertEqual(shown["overlaps"][0], {"sources": ["hypothesis-basket", "ranks"], "keys": 7})
        self.assertIn({"sources": ["ads-keyword", "tracking-file"], "keys": 1}, shown["overlaps"])
        self.assertEqual(shown["twins"], [{"market": "ua", "keywords": ["a'b", "a’b"]}])

    def test_candidates_come_most_named_first_then_in_a_fixed_order(self):
        write(self.store, "keywords/tracking-us.txt", "zeta\nalpha\nmid\n")
        write(self.store, "ads/us_reviewed/keywords.txt", "mid\nbeta\n")
        shown = kr.summary(list(built(self.store).values()))
        self.assertEqual([c["keyword"] for c in shown["candidates"]], ["mid", "alpha", "beta", "zeta"])


class Command(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = copy_store(self._tmp.name)

    def test_build_show_and_add_through_the_cli(self):
        code, out, err = run("copilot.py", "keywords", "registry", "build", "--store", str(self.store), "--as-of", AS_OF)
        self.assertEqual((code, err), (0, ""), out)
        self.assertIn("appended 10", out)
        self.assertIn("refused 2 brand keys (never tracked): ua tidepool, us tidepool", out)
        code, out, _ = run("copilot.py", "keywords", "registry", "build", "--store", str(self.store), "--as-of", AS_OF)
        self.assertIn("appended 0", out)
        code, out, _ = run("copilot.py", "keywords", "registry", "add", "--store", str(self.store), "--as-of", AS_OF,
                           "--market", "us", "--source", "google-suggest", "tide chart", "tide app")
        self.assertEqual(code, 0)
        self.assertIn("appended 2", out)
        code, out, _ = run("copilot.py", "keywords", "registry", "show", "--store", str(self.store), "--json")
        shown = json.loads(out)
        self.assertEqual((code, shown["keys"]), (0, 12))
        self.assertEqual(shown["by_source"]["google-suggest"], 2)

    def test_record_on_the_network_commands_files_what_they_found_with_its_source(self):
        import argparse
        import contextlib
        import io
        from unittest import mock

        import harvest_keywords
        from aso.commands import keywords

        said = argparse.Namespace(term="tide", country="us", store=str(self.store), record=True, json=True, limit=25, seeds="tide")
        with mock.patch.object(harvest_keywords, "fetch_hints", return_value=["tide chart", "tide app"]), \
                mock.patch.object(harvest_keywords, "fetch_competitors", return_value=[("Tide Rival", 3)]), \
                contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(keywords.cmd_keywords_hints(said), 0)
            self.assertEqual(keywords.cmd_keywords_competitors(said), 0)
        self.assertIn('"hints"', out.getvalue())                    # --json output is still whole; the note went to stderr
        rows = {(r["market"], r["key_norm"]): r["sources"] for r in kr.read_registry(self.store)}
        self.assertEqual(rows[("us", "tide chart")], "autocomplete-hints")
        self.assertEqual(rows[("us", "tide rival")], "competitor-harvest")

    def test_show_without_a_registry_says_what_to_run(self):
        code, out, _ = run("copilot.py", "keywords", "registry", "show", "--store", str(self.store))
        self.assertEqual(code, 1)
        self.assertIn("keywords registry build", out)

    def test_the_sample_store_is_never_written(self):
        run("copilot.py", "keywords", "registry", "build", "--store", str(self.store), "--as-of", AS_OF)
        self.assertFalse((ROOT / "assets" / "sample" / "store" / kr.REGISTRY).exists())


class Offline(unittest.TestCase):
    def test_the_registry_has_no_network_and_no_clock(self):
        path = ROOT / "scripts" / "aso" / "keyword_registry.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {n.split(".")[0] for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
                 for n in ([a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""])}
        self.assertEqual(names & {"urllib", "http", "socket", "subprocess", "requests"}, set())
        clock = [node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
                 and node.attr in ("today", "now", "utcnow", "time", "monotonic")]
        self.assertEqual(clock, [])


if __name__ == "__main__":
    unittest.main()
