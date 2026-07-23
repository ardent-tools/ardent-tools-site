"""Focused regressions for release identity, cache, tape, and player contracts."""

from __future__ import annotations

import hashlib
import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "bin" / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


site = load_script("ardent_validate_site", "validate-site.py")
production = load_script("ardent_verify_production", "verify-production.py")
catalog = load_script("ardent_generate_catalog", "generate-systems-json.py")
resume_fonts = load_script("ardent_resume_fonts", "validate-resume-fonts.py")

BASE_URL = "https://ardent.tools"
EXPECTED_REVISION = "2" * 40
ASSET_EPOCH = "2"
CSS_BODY = b"body { color: #231f20; }\n"
JS_BODY = b"document.documentElement.dataset.ready = 'true';\n"
CSS_HASH = hashlib.sha256(CSS_BODY).hexdigest()[:20]
JS_HASH = hashlib.sha256(JS_BODY).hexdigest()[:20]
CSS_URL = f"{BASE_URL}/css/site.css?h={CSS_HASH}&v={ASSET_EPOCH}"
JS_URL = f"{BASE_URL}/js/site.js?h={JS_HASH}&v={ASSET_EPOCH}"
GOOD_CACHE = "no-store, no-transform"
GOOD_CSP = "default-src 'self'; script-src 'self'"


def run_production_fixture(
    test: unittest.TestCase,
    *,
    revision: str = EXPECTED_REVISION,
    revision_cache: str = "no-store, no-transform",
    css_body: bytes = CSS_BODY,
    css_cache: str = GOOD_CACHE,
    js_body: bytes = JS_BODY,
    js_cache: str = GOOD_CACHE,
    js_status: int = 200,
) -> list[str]:
    assets = (
        f'<link rel="stylesheet" href="{CSS_URL}">'
        f'<script src="{JS_URL}" defer></script>'
    )
    responses = {
        (f"{BASE_URL}/build-revision.txt", True): (
            200,
            {"Cache-Control": revision_cache},
            f"{revision}\n".encode(),
        ),
        (f"{BASE_URL}/sitemap.xml", True): (
            200,
            {"Cache-Control": GOOD_CACHE},
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                f"<url><loc>{BASE_URL}/</loc></url>"
                f"<url><loc>{BASE_URL}/evidence/</loc></url>"
                "</urlset>"
            ).encode(),
        ),
        **{
            (f"{BASE_URL}{path}", False): (
                200,
                {"Cache-Control": GOOD_CACHE},
                b"structured resource\n",
            )
            for path in production.STRUCTURED_RESOURCE_PATHS
        },
        (f"{BASE_URL}/", True): (
            200,
            {"Cache-Control": GOOD_CACHE, "Content-Security-Policy": GOOD_CSP},
            assets.encode(),
        ),
        (f"{BASE_URL}/evidence/", True): (
            200,
            {"cache-control": GOOD_CACHE, "content-security-policy": GOOD_CSP},
            (
                '<link rel="canonical" href="https://ardent.tools/evidence/">'
                "Evidence register 0 published casts."
                f"{assets}"
            ).encode(),
        ),
        (CSS_URL, False): (200, {"CACHE-CONTROL": css_cache}, css_body),
        (JS_URL, False): (js_status, {"Cache-Control": js_cache}, js_body),
        (f"{BASE_URL}/demos/", False): (301, {"Location": "/evidence/"}, b""),
    }
    calls: list[tuple[str, bool]] = []

    def response(url: str, _timeout: float, follow: bool = True):
        key = (url, follow)
        calls.append(key)
        test.assertIn(key, responses, f"unexpected or duplicate request: {key!r}")
        return responses.pop(key)

    with mock.patch.object(production, "request", side_effect=response):
        errors = production.verify(BASE_URL, 1.0, EXPECTED_REVISION, ASSET_EPOCH)
    test.assertEqual(responses, {}, f"required URLs were not requested: {responses!r}")
    test.assertEqual(len(calls), 7 + len(production.STRUCTURED_RESOURCE_PATHS))
    return errors


class RevisionContractTests(unittest.TestCase):
    def test_older_well_formed_artifact_fails_expected_revision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            output.joinpath("build-revision.txt").write_text("1" * 40 + "\n")
            errors: list[str] = []
            site.validate_revision(errors, output, "2" * 40)
            self.assertTrue(any("mismatch" in error for error in errors), errors)

    def test_live_verifier_rejects_older_compatible_deployment(self) -> None:
        errors = run_production_fixture(self, revision="1" * 40)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("deployed revision mismatch", errors[0])


class ProductionAssetContractTests(unittest.TestCase):
    def test_matching_authored_asset_bodies_pass(self) -> None:
        self.assertEqual(run_production_fixture(self), [])

    def test_stale_body_at_exact_authored_url_fails_digest(self) -> None:
        errors = run_production_fixture(self, js_body=b"stale JavaScript body\n")
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("authored JavaScript asset digest mismatch", errors[0])
        self.assertIn(JS_URL, errors[0])

    def test_immutable_asset_cache_policy_fails(self) -> None:
        errors = run_production_fixture(
            self,
            js_cache="public, max-age=0, must-revalidate, no-transform, immutable",
        )
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("must be exactly no-store, no-transform", errors[0])

    def test_non_200_authored_asset_fails(self) -> None:
        errors = run_production_fixture(self, js_status=404, js_body=b"not found")
        self.assertEqual(len(errors), 1, errors)
        self.assertIn(f"{JS_URL!r} returned 404, expected 200", errors[0])

    def test_revision_cache_policy_rejects_immutable(self) -> None:
        errors = run_production_fixture(
            self, revision_cache="NO-STORE, NO-TRANSFORM, IMMUTABLE"
        )
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("/build-revision.txt Cache-Control must be exactly", errors[0])

    def test_missing_malformed_and_external_asset_hashes_fail(self) -> None:
        errors: list[str] = []
        body = (
            '<link rel="stylesheet" href="/css/missing.css">'
            '<script src="/js/bad.js?h=ABC&amp;v=2"></script>'
            '<script src="https://example.com/app.js?h=11111111111111111111&amp;v=2"></script>'
        )
        assets = production.collect_hashed_assets(
            errors, f"{BASE_URL}/", f"{BASE_URL}/", body, ASSET_EPOCH
        )
        self.assertEqual(assets, [])
        self.assertEqual(len(errors), 3, errors)
        self.assertTrue(any("exactly one h and one v" in error for error in errors), errors)
        self.assertTrue(any("malformed h" in error for error in errors), errors)
        self.assertTrue(any("external JavaScript" in error for error in errors), errors)

    def test_page_missing_css_and_javascript_references_fails(self) -> None:
        errors: list[str] = []
        assets = production.collect_hashed_assets(
            errors,
            f"{BASE_URL}/",
            f"{BASE_URL}/",
            "<main>Evidence register</main>",
            ASSET_EPOCH,
        )
        self.assertEqual(assets, [])
        self.assertEqual(len(errors), 2, errors)
        self.assertTrue(any("no authored CSS" in error for error in errors), errors)
        self.assertTrue(any("no authored JavaScript" in error for error in errors), errors)

    def test_conflicting_hashes_for_one_asset_path_fail(self) -> None:
        other_hash = "1" * 20
        other_url = f"{BASE_URL}/js/site.js?h={other_hash}&v={ASSET_EPOCH}"
        errors: list[str] = []
        assets = production.distinct_assets(
            errors,
            [
                (JS_URL, JS_HASH, "JavaScript"),
                (other_url, other_hash, "JavaScript"),
            ],
        )
        self.assertEqual(set(assets), {JS_URL, other_url})
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("conflicting authored hashes for /js/site.js", errors[0])

    def test_live_max_age_and_duplicate_policy_fail(self) -> None:
        errors: list[str] = []
        production.validate_no_store_cache(
            errors,
            "/",
            {
                "Cache-Control": (
                    "PUBLIC, MAX-AGE = 0, MUST-REVALIDATE, NO-TRANSFORM, max-age=31536000"
                )
            },
        )
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("must be exactly no-store, no-transform", errors[0])

    def test_asset_epoch_and_query_shape_fail_closed(self) -> None:
        cases = {
            "missing hash": "/js/site.js?v=2",
            "missing epoch": f"/js/site.js?h={JS_HASH}",
            "empty hash": "/js/site.js?h=&v=2",
            "wrong epoch": f"/js/site.js?h={JS_HASH}&v=1",
            "empty epoch": f"/js/site.js?h={JS_HASH}&v=",
            "duplicate epoch": f"/js/site.js?h={JS_HASH}&v=2&v=2",
            "duplicate hash": f"/js/site.js?h={JS_HASH}&h={JS_HASH}&v=2",
            "unexpected query": f"/js/site.js?h={JS_HASH}&v=2&x=1",
        }
        for label, reference in cases.items():
            with self.subTest(label=label):
                errors: list[str] = []
                production.collect_hashed_assets(
                    errors,
                    f"{BASE_URL}/",
                    f"{BASE_URL}/",
                    f'<link rel="stylesheet" href="{CSS_URL}"><script src="{reference}"></script>',
                    ASSET_EPOCH,
                )
                self.assertEqual(len(errors), 1, errors)

    def test_every_forbidden_cache_directive_and_duplicate_fail(self) -> None:
        policies = (
            "no-store, no-transform, max-age=0",
            "no-store, no-transform, s-maxage=0",
            "no-store, no-transform, public",
            "no-store, no-transform, private",
            "no-store, no-transform, must-revalidate",
            "no-store, no-transform, immutable",
            "no-store, no-transform, no-store",
        )
        for policy in policies:
            with self.subTest(policy=policy):
                errors: list[str] = []
                production.validate_no_store_cache(
                    errors, "/resource", {"Cache-Control": policy}
                )
                self.assertEqual(len(errors), 1, errors)


class CacheContractTests(unittest.TestCase):
    def test_single_global_no_store_policy_covers_overlapping_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            output.joinpath("css").mkdir()
            output.joinpath("css/site.css").write_text("body{}")
            errors: list[str] = []
            site.validate_cache_contract(
                errors,
                output,
                "/*\n  Cache-Control: no-store, no-transform\n",
            )
        self.assertEqual(errors, [])

    def test_overlapping_cache_values_are_rejected(self) -> None:
        headers = """/*
  Cache-Control: no-store, no-transform
/css/*
  Cache-Control: no-store, no-transform
"""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            output.joinpath("css").mkdir()
            output.joinpath("css/site.css").write_text("body{}")
            errors: list[str] = []
            site.validate_cache_contract(errors, output, headers)
        self.assertTrue(any("2 effective Cache-Control" in error for error in errors), errors)

    def test_immutable_stable_asset_is_rejected(self) -> None:
        headers = """/*
  Cache-Control: public, max-age=31536000, immutable, no-transform
"""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            output.joinpath("img").mkdir()
            output.joinpath("img/art.png").write_bytes(b"png")
            errors: list[str] = []
            site.validate_cache_contract(errors, output, headers)
        self.assertTrue(any("must be exactly no-store, no-transform" in error for error in errors), errors)

    def test_revision_sentinel_must_be_no_store(self) -> None:
        headers = """/*
  Cache-Control: public, max-age=60, no-transform
"""
        with tempfile.TemporaryDirectory() as directory:
            errors: list[str] = []
            site.validate_cache_contract(errors, Path(directory), headers)
        self.assertTrue(any("must be exactly no-store, no-transform" in error for error in errors), errors)


class RecordingContractTests(unittest.TestCase):
    def test_unsafe_tape_and_typed_success_token_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tape = Path(directory) / "hamma-tests.tape"
            tape.write_text(
                "# Run from the ardent-tools-site root\n"
                "# ARDENT_HAMMA_ROOT=/repo vhs static/tapes/hamma-tests.tape\n"
                'Type "test -n \\"$ARDENT_HAMMA_ROOT\\""\n'
                'Type "cd \\"$ARDENT_HAMMA_ROOT\\""\n'
                'Type "sudo apt-get install x && echo HAMMA_TESTS_OK"\n'
                "Wait+Screen /HAMMA_TESTS_OK/\n"
            )
            errors: list[str] = []
            site.validate_tape_contract(errors, tape)
        self.assertTrue(any("forbidden recording behavior" in error for error in errors), errors)
        self.assertTrue(any("visible in a typed command" in error for error in errors), errors)

    def test_positive_cast_requires_complete_rendered_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "public"
            static = root / "static"
            system_page = output / "systems/demo/index.html"
            catalog_page = output / "systems/index.html"
            evidence_page = output / "evidence/index.html"
            cast_file = static / "casts/demo.cast"
            player_css = output / "vendor/asciinema/asciinema-player.css"
            player_js = output / "vendor/asciinema/asciinema-player.min.js"
            for path in (
                system_page,
                catalog_page,
                evidence_page,
                cast_file,
                player_css,
                player_js,
            ):
                path.parent.mkdir(parents=True, exist_ok=True)
            cast_file.write_text("{}\n")
            player_css.write_bytes(CSS_BODY)
            player_js.write_bytes(JS_BODY)
            cast = "/casts/demo.cast"
            system_markup = (
                f'<div data-cast="{cast}"></div>'
                f'<link rel="stylesheet" href="/vendor/asciinema/asciinema-player.css?h={CSS_HASH}&amp;v=2">'
                f'<script src="/vendor/asciinema/asciinema-player.min.js?h={JS_HASH}&amp;v=2"></script>'
            )
            catalog_markup = (
                '<a href="https://ardent.tools/systems/demo/">WATCH RECORDING</a>'
            )
            evidence_markup = '<a href="https://ardent.tools/systems/demo/">demo recording</a>'
            html = {
                system_page: system_markup,
                catalog_page: catalog_markup,
                evidence_page: evidence_markup,
            }
            errors: list[str] = []
            site.validate_asset_contract(errors, {system_page: system_markup}, output, ASSET_EPOCH)
            site.validate_player_contract(
                errors,
                [(Path("content/systems/demo.md"), cast)],
                html,
                "script-src 'self' 'wasm-unsafe-eval'",
                output,
                static,
            )
            self.assertEqual(errors, [])

            wrong_epoch_markup = system_markup.replace("&amp;v=2", "&amp;v=1")
            errors = []
            site.validate_asset_contract(
                errors, {system_page: wrong_epoch_markup}, output, ASSET_EPOCH
            )
            self.assertEqual(len(errors), 2, errors)
            self.assertTrue(all("expected '2'" in error for error in errors), errors)

            broken = dict(html)
            broken[system_page] = f'<div data-cast="{cast}"></div>'
            errors = []
            site.validate_player_contract(
                errors,
                [(Path("content/systems/demo.md"), cast)],
                broken,
                "script-src 'self' 'wasm-unsafe-eval'",
                output,
                static,
            )
            self.assertTrue(any("conditional player CSS/JS" in error for error in errors), errors)


class CatalogContractTests(unittest.TestCase):
    def test_ambiguous_agpl_identifier_is_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            catalog.exact_license("sphragis", "AGPL-3.0")


class ResumeFontContractTests(unittest.TestCase):
    def test_changed_font_bytes_fail_pinned_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            font_dir = Path(directory)
            for name in (*resume_fonts.EXPECTED_FILES, "SHA256SUMS"):
                shutil.copy2(ROOT / "resume/fonts" / name, font_dir / name)
            with (font_dir / "NimbusSans-Regular.otf").open("ab") as handle:
                handle.write(b"changed")
            errors = resume_fonts.validate_inputs(font_dir)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("hash mismatch for NimbusSans-Regular.otf", errors[0])

    def test_unexpected_embedded_font_fails_closed(self) -> None:
        report = (
            "name type encoding emb sub uni object ID\n"
            "-----------------------------------------\n"
            "ABCDEF+DejaVuSansMono-Identity-H CID Type 0C Identity-H yes yes yes 1 0\n"
        )
        errors = resume_fonts.validate_pdffonts(report)
        self.assertTrue(any("embedded font set differs" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
