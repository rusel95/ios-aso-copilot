"""The page's rendering, checked without a browser: the built page's own script is run by Node, and a test reads
the HTML it returns for a route. Skipped when Node is not installed; the page needs no Node to be built or opened."""
import html as html_module
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.helpers import AS_OF, ROOT, exported_store  # noqa: E402

from aso.dashboard import site  # noqa: E402

NODE = shutil.which("node")


def text_of(markup: str) -> str:
    """What a reader sees: tags dropped, entities decoded, whitespace collapsed."""
    return " ".join(html_module.unescape(re.sub(r"<[^>]+>", " ", markup)).split())


@unittest.skipUnless(NODE, "node is not installed; the page's rendering is not checked here")
class PageCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import contextlib
        import io
        cls.tmp = tempfile.TemporaryDirectory()
        store = exported_store(cls.tmp.name)
        with contextlib.redirect_stdout(io.StringIO()):
            assert site.build(store / "data", Path(cls.tmp.name) / "public", "Tidepool") == 0
        cls.page = Path(cls.tmp.name) / "public" / "index.html"

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def js(self, expression: str) -> str:
        done = subprocess.run([NODE, str(ROOT / "tests" / "page_smoke.js"), str(self.page), expression],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr[-600:])
        return done.stdout

    def render(self, route: str, today: str = AS_OF) -> str:
        return self.js(f"ASO.render({route!r}, payload, {today!r})")

    def read(self, route: str, today: str = AS_OF) -> str:
        return text_of(self.render(route, today))


class Shell(PageCase):
    def test_escape(self):
        self.assertEqual(self.js("ASO.esc('<b>x</b> & \"y\"')"), "&lt;b&gt;x&lt;/b&gt; &amp; &quot;y&quot;")

    def test_series_of_a_flow(self):
        self.assertEqual(self.js("ASO.series(payload, 'store_funnel.impressions').map(function (e) { return e.value; })"),
                         "[1000,1200,1500]")
        self.assertEqual(self.js("ASO.series(payload, 'money.proceeds_usd').map(function (e) { return e.unavailable.code; })"),
                         '["no_source","no_source","no_source"]')

    def test_series_of_a_stock_holds_only_the_days_it_was_read(self):
        self.assertEqual(self.js("ASO.series(payload, 'ranks.keys_read').map(function (e) { return e.id + ':' + e.value; })"),
                         '["2026-10-05:8","2026-10-19:8","2026-11-02:9","2026-11-09:2"]')
        self.assertEqual(self.js("ASO.series(payload, 'ratings.ratings_count')"), "[]")

    def test_the_navigation_marks_the_current_tab(self):
        nav = self.js("ASO.nav('#/keywords')")
        self.assertRegex(nav, r'<a href="#/keywords" aria-current="page">Keywords</a>')
        self.assertEqual(nav.count('aria-current="page"'), 1)
        self.assertEqual(re.findall(r">([^<]+)</a>", nav), ["Overview", "Ledger", "Keywords", "Store funnel", "Money",
                                                          "Apple Ads", "In-app", "How data gets here"])

    def test_an_unknown_route_says_so(self):
        self.assertIn("No such page", self.read("#/nope"))

    def test_numbers_are_formatted_by_unit(self):
        self.assertEqual(self.js("[ASO.fmt(1500, 'count'), ASO.fmt(0.444444, 'ratio'), ASO.fmt(-59.9, 'usd'), "
                                 "ASO.fmt(85.71, 'per_100'), ASO.fmt(4.5, 'stars'), ASO.fmt(12345.6, 'usd')]"),
                         '["1,500","44.4%","−$59.90","85.7","4.50","$12,345.60"]')


class Overview(PageCase):
    def test_sources_and_their_age(self):
        seen = self.read("#/")
        self.assertIn("Keyword ranks 2026-11-09 5 d", seen)
        self.assertIn("Store funnel 2026-11-10 4 d", seen)
        self.assertIn("Apple search popularity 2026-11-03 11 d", seen)
        self.assertNotIn('class="age stale"', self.render("#/"))       # no source is marked stale

    def test_a_source_nothing_stores_says_so(self):
        seen = self.read("#/")
        for name in ("Subscriptions", "Ratings and reviews", "In-app", "Money", "Apple Ads", "Install lifecycle"):
            with self.subTest(source=name):
                self.assertIn(f"{name} Not stored yet", seen)

    def test_a_source_older_than_two_weeks_is_stale(self):
        seen = self.read("#/", "2026-12-01")
        self.assertIn("Keyword ranks 2026-11-09 22 d · stale", seen)
        self.assertIn("Store funnel 2026-11-10 21 d · stale", seen)

    def test_headline_tiles(self):
        seen = self.read("#/")
        self.assertIn("Hypotheses 8 4 judged · 2 due · 1 open · 1 not shipped", seen)
        self.assertIn("Keys in top 30 4 of 9 keys read · 2 in top 10 · sweep of 2026-11-02", seen)
        self.assertIn("First-time downloads 64 1,500 impressions · 4.3% download · week of 2026-11-02", seen)

    def test_headline_ranks_skip_a_partial_sweep(self):
        # the newest sweep (11-09) read 2 of 10 tracked keys; the headline stays on the last full one
        self.assertNotIn("sweep of 2026-11-09", self.read("#/"))

    def test_a_missing_figure_is_words_never_a_zero(self):
        markup = self.render("#/")
        for label in ("MRR", "Net cashflow", "Deletions per 100 installs"):
            with self.subTest(tile=label):
                tile = re.search(r'<section class="tile">\s*<h3>' + re.escape(label) + r"</h3>(.*?)</section>", markup, re.S)
                self.assertIsNotNone(tile, label)
                self.assertIn("Not stored yet", text_of(tile.group(1)))
                self.assertIsNone(re.search(r"\b0\b", text_of(tile.group(1))))

    def test_a_figure_is_a_button_that_names_itself(self):
        markup = self.render("#/")
        self.assertRegex(markup, r'<button class="fig" data-fig="store_funnel.first_downloads" data-period="2026-11-02"[^>]*>64</button>')

    def test_summary_blocks_link_to_their_tabs(self):
        markup = self.render("#/")
        for route in ("#/ledger", "#/keywords", "#/funnel"):
            self.assertIn(f'href="{route}"', markup)
        seen = text_of(markup)
        self.assertIn("2 due", seen)
        self.assertIn("H005", seen)


class Panel(PageCase):
    def test_a_ratio_shows_its_two_totals_its_definition_and_its_source(self):
        seen = text_of(self.js("ASO.panel(payload, 'store_funnel.page_cvr', '2026-11-02')"))
        self.assertIn("Page views that download", seen)
        self.assertIn("40.0%", seen)
        self.assertIn("64 of 160 (first-time downloads over product page views)", seen)
        self.assertIn("First-time downloads divided by product page views", seen)
        self.assertIn("asc-analytics", seen)
        self.assertIn("fetched 2026-11-10", seen)
        self.assertIn("Measured", seen)

    def test_a_missing_figure_shows_its_reason_and_code(self):
        seen = text_of(self.js("ASO.panel(payload, 'money.proceeds_usd', '2026-11-02')"))
        self.assertIn("Not stored yet", seen)
        self.assertIn("Proceeds and Apple Ads spend are not stored by week yet.", seen)
        self.assertIn("no_source", seen)

    def test_a_split_by_storefront_is_listed(self):
        seen = text_of(self.js("ASO.panel(payload, 'store_funnel.impressions', '2026-11-02')"))
        self.assertIn("ua 600", seen)
        self.assertIn("us 900", seen)


if __name__ == "__main__":
    unittest.main()
