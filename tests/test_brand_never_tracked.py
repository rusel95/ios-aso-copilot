"""A brand query is never tracked: not asked of Apple, not written to ranks.csv, and removable where it already sits."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from aso.ledger_ingest import drop_brand, ingest, refresh_basket  # noqa: E402
from aso.store import RANK_HEADER, read_ranks  # noqa: E402


def store_with(tmp: str, tokens: str) -> Path:
    store = Path(tmp)
    (store / "metrics").mkdir()
    (store / "config.md").write_text(f"**Brand tokens**: {tokens}\n", encoding="utf-8")
    return store


class BrandIsNeverTracked(unittest.TestCase):
    def test_the_sweep_does_not_ask_for_a_brand_key(self):
        rows = [{"date": "2026-11-02", "market": "de", "keyword": k, "group": "target", "status": "ok"}
                for k in ("tidepool", "tidepool: fotos komprimieren", "fotos komprimieren", "tidepoolish")]
        basket, _ = refresh_basket(rows, None, failed_only=False, brands=["tidepool"])
        # a whole word is the brand; a generic word that merely contains its letters is not
        self.assertEqual(basket, {"de": ["fotos komprimieren", "tidepoolish"]})

    def test_a_snapshot_cannot_put_a_brand_key_into_the_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = store_with(tmp, "tidepool")
            snap = store / "s.json"
            snap.write_text(json.dumps([
                {"country_code": "de", "term": "tidepool", "our_rank": 1, "total_results": 200},
                {"country_code": "de", "term": "fotos komprimieren", "our_rank": 40, "total_results": 200},
            ]), encoding="utf-8")
            self.assertEqual(ingest(store, snap, "2026-11-02", "itunes-search-api", 200, "target"), 1)
            self.assertEqual([r["keyword"] for r in read_ranks(store)], ["fotos komprimieren"])

    def test_a_store_that_already_tracks_one_can_drop_it_and_keeps_every_other_byte(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = store_with(tmp, "tidepool")
            lines = [",".join(RANK_HEADER) + "\r\n",
                     "2026-11-02,de,tidepool,target,1,,,itunes-search-api,200,ok\r\n",
                     "2026-11-02,de,fotos komprimieren,target,40,,,itunes-search-api,200,ok\n",   # an older LF line
                     '2026-11-02,de,"a, b",target,,,,itunes-search-api,200,beyond-depth\r\n']
            (store / "metrics" / "ranks.csv").write_bytes("".join(lines).encode())
            self.assertEqual(drop_brand(store), 1)
            self.assertEqual((store / "metrics" / "ranks.csv").read_bytes().decode(), "".join(lines[:1] + lines[2:]))
            self.assertEqual(drop_brand(store), 0)

    def test_without_brand_tokens_nothing_is_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp)
            (store / "metrics").mkdir()
            (store / "metrics" / "ranks.csv").write_text(",".join(RANK_HEADER) + "\n", encoding="utf-8")
            self.assertEqual(drop_brand(store), 0)


if __name__ == "__main__":
    unittest.main()
