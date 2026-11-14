"""The page build: one self-contained file, the same bytes every time, and nothing written from bad data."""
import base64
import contextlib
import hashlib
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.helpers import ROOT, copy_store, exported_store, run  # noqa: E402

from aso.dashboard import contract, site  # noqa: E402


def build(store, out, name="Tidepool"):
    with contextlib.redirect_stdout(io.StringIO()):          # the build reports on stdout; a test asserts, not prints
        return site.build(store / "data", out, name)


def page(tmp, name="Tidepool"):
    store, out = exported_store(tmp), Path(tmp) / "public"
    assert build(store, out, name) == 0
    return (out / "index.html").read_text(encoding="utf-8")


def payload_of(html):
    return json.loads(re.search(r'<script id="payload" type="application/json">(.*?)</script>', html, re.S).group(1))


class Build(unittest.TestCase):
    def test_build_is_byte_identical_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = exported_store(tmp)
            first, second = Path(tmp) / "one", Path(tmp) / "two"
            self.assertEqual((build(store, first), build(store, second)), (0, 0))
            self.assertEqual((first / "index.html").read_bytes(), (second / "index.html").read_bytes())

    def test_the_payload_holds_the_data_and_nothing_of_the_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = payload_of(page(tmp))
        self.assertEqual(sorted(payload), ["catalog", "events", "hypotheses", "keys", "name", "places", "snapshots", "weeks"])
        self.assertEqual(payload["name"], "Tidepool")
        self.assertEqual([w["period"]["id"] for w in payload["weeks"]], ["2026-10-19", "2026-10-26", "2026-11-02"])
        self.assertEqual(len(payload["snapshots"]), 5)
        self.assertEqual(len(payload["hypotheses"]["hypotheses"]), 8)

    def test_invalid_file_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, out = exported_store(tmp), Path(tmp) / "public"
            bad = store / "data" / "week" / "2026-11-02.json"
            bad.write_text(bad.read_text(encoding="utf-8").replace('"impressions"', '"impresions"'), encoding="utf-8")
            code, text, _ = run("build_site.py", "--data", str(store / "data"), "--out", str(out))
            self.assertEqual(code, 1)
            self.assertIn("INVALID week/2026-11-02.json: unknown figure store_funnel.impresions", text)
            self.assertEqual(text.splitlines()[-1], "FAIL data")
            self.assertFalse(out.exists())

    def test_a_missing_entity_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, out = exported_store(tmp), Path(tmp) / "public"
            (store / "data" / "keys.json").unlink()
            self.assertEqual(build(store, out), 1)
            self.assertFalse(out.exists())

    def test_no_data_folder_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            self.assertEqual(build(store, Path(tmp) / "public"), 1)

    def test_csp_hashes_match_inlined_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            html = page(tmp)
        policy = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', html).group(1)
        style = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
        script = re.findall(r"<script>(.*?)</script>", html, re.S)[-1]

        def digest(text):
            return "'sha256-" + base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode() + "'"

        self.assertIn(f"style-src {digest(style)}", policy)
        self.assertIn(f"script-src {digest(script)}", policy)
        self.assertIn("default-src 'none'", policy)
        self.assertNotIn("unsafe", policy)

    def test_payload_cannot_close_its_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            with (store / "metrics" / "ranks.csv").open("a", encoding="utf-8") as fh:
                fh.write("2026-11-02,us,a</script><script>alert(1),target,5,,,itunes-search-api,200,ok\n")
            import datetime as dt
            from aso.dashboard import export
            files, _ = export.build_all(store, dt.date(2026, 11, 14))
            export.write(store, files)
            out = Path(tmp) / "public"
            self.assertEqual(build(store, out), 0)
            html = (out / "index.html").read_text(encoding="utf-8")
        self.assertEqual(html.count("</script>"), 2)
        self.assertIn("a</script><script>alert(1)", [k["keyword"] for k in payload_of(html)["keys"]["keys"]])

    def test_no_outside_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            html = page(tmp)
        self.assertIsNone(re.search(r"""(?:src|href)\s*=\s*["']?(?:https?:)?//""", html))
        for banned in ("@import", "url(", "<link", "<img", "<iframe", "<object", "<embed"):
            self.assertNotIn(banned, html)

    def test_no_inline_style_attribute(self):
        # the policy allows one hashed style sheet; a style="" attribute would be refused by the browser
        assets = ROOT / "assets" / "dashboard"
        source = "".join(p.read_text(encoding="utf-8") for p in [assets / "template.html", *sorted((assets / "js").glob("*.js"))])
        self.assertNotIn("style=", source)

    def test_every_catalog_figure_has_a_place(self):
        catalog = contract.load_catalog()
        places = json.loads((ROOT / "assets" / "dashboard" / "places.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(places), ["ads", "funnel", "how", "in_app", "keywords", "ledger", "money", "overview"])
        placed = {key for keys in places.values() for key in keys}
        known = {f"{family}.{key}" for family, spec in catalog["families"].items() for key in spec["figures"]}
        self.assertEqual(placed, known)


class Commands(unittest.TestCase):
    def test_build_site_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, out = exported_store(tmp), Path(tmp) / "public"
            code, text, err = run("build_site.py", "--data", str(store / "data"), "--out", str(out), "--name", "Tidepool")
            self.assertEqual(code, 0, text + err)
            size = (out / "index.html").stat().st_size
            self.assertEqual(text.splitlines()[-1], f"PASS site (11 files, {size} bytes)")

    def test_copilot_build_names_the_app_from_its_brand_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = exported_store(tmp)
            code, text, err = run("copilot.py", "build", "--store", str(store), "--out", str(Path(tmp) / "site"))
            self.assertEqual(code, 0, text + err)
            html = (Path(tmp) / "site" / "index.html").read_text(encoding="utf-8")
            self.assertEqual(payload_of(html)["name"], "Tidepool")


if __name__ == "__main__":
    unittest.main()
