"""Pure rank logic on the sample store: bands of one sweep, movers, and how a query finds its key."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.helpers import SAMPLE  # noqa: E402

from aso.ranks import key_of, movers, series, sweep_bands  # noqa: E402
from aso.store import read_ranks  # noqa: E402

BRAND = ["tidepool"]


class SweepBands(unittest.TestCase):
    def test_bands_on_a_full_sweep(self):
        b = sweep_bands(read_ranks(SAMPLE), BRAND, "2026-11-02")
        self.assertEqual((b["tracked_keys"], b["keys_read"]), (10, 9))
        self.assertEqual((b["top10"], b["top30"], b["top100"], b["top200"], b["beyond"]), (2, 2, 3, 1, 1))
        self.assertEqual((b["no_results"], b["errors"]), (1, 0))
        self.assertEqual(b["by_market"]["ua"]["top10"], 1)
        self.assertEqual((b["by_market"]["us"]["keys_read"], b["by_market"]["ua"]["keys_read"]), (5, 4))

    def test_bands_on_the_first_sweep(self):
        b = sweep_bands(read_ranks(SAMPLE), BRAND, "2026-10-05")
        self.assertEqual((b["keys_read"], b["top10"], b["top30"], b["top100"], b["top200"], b["beyond"]),
                         (8, 1, 1, 3, 1, 2))
        self.assertEqual((b["no_results"], b["errors"]), (1, 1))

    def test_bands_on_a_partial_sweep(self):
        b = sweep_bands(read_ranks(SAMPLE), BRAND, "2026-11-09")
        self.assertEqual((b["tracked_keys"], b["keys_read"]), (10, 2))

    def test_brand_keys_are_left_out(self):
        with_brand = sweep_bands(read_ranks(SAMPLE), [], "2026-11-02")
        self.assertEqual((with_brand["tracked_keys"], with_brand["top10"]), (12, 4))

    def test_a_correction_on_the_same_date_wins(self):
        rows = read_ranks(SAMPLE)
        retry = dict(next(r for r in rows if r["date"] == "2026-10-05" and r["keyword"] == "sea level"))
        retry.update(position=150, status="ok")
        b = sweep_bands(rows + [retry], BRAND, "2026-10-05")
        self.assertEqual((b["errors"], b["top200"], b["keys_read"]), (0, 2, 9))


class Movers(unittest.TestCase):
    def test_largest_gain_first(self):
        rows = movers(series(read_ranks(SAMPLE)), BRAND)
        first = rows[0]
        self.assertEqual((first["market"], first["keyword"], first["first"], first["last"], first["delta"]),
                         ("us", "tide times", 120, 60, 60))
        self.assertEqual(first["label"], "improved")

    def test_a_key_that_entered_has_no_number(self):
        rows = {(r["market"], r["keyword"]): r for r in movers(series(read_ranks(SAMPLE)), BRAND)}
        entered = rows[("us", "surf forecast")]
        self.assertIsNone(entered["delta"])
        self.assertTrue(entered["label"].startswith("ENTERED"))

    def test_brand_keys_are_left_out(self):
        self.assertFalse([r for r in movers(series(read_ranks(SAMPLE)), BRAND) if r["keyword"] == "tidepool"])


class KeyOf(unittest.TestCase):
    def test_apostrophe_forms_are_one_key(self):
        self.assertEqual(key_of("ua", "п'ятниця море"), key_of("UA", "п’ятниця  Море"))

    def test_composed_and_decomposed_letters_are_one_key(self):
        self.assertEqual(key_of("fr", "vidéo"), key_of("fr", "vidéo"))


if __name__ == "__main__":
    unittest.main()
