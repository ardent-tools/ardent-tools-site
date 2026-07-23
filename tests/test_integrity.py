"""Focused regressions for release identity, cache, tape, and player contracts."""

from __future__ import annotations

import hashlib
import importlib.util
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

BASE_URL = "https://ardent.tools"
EXPECTED_REVISION = "2" * 40
CSS_BODY = b"body { color: #231f20; }\n"
JS_BODY = b"document.documentElement.dataset.ready = 'true';\n"
CSS_HASH = hashlib.sha256(CSS_BODY).hexdigest()[:20]
JS_HASH = hashlib.sha256(JS_BODY).hexdigest()[:20]
CSS_URL = f"{BASE_URL}/css/site.css?h={CSS_HASH}"
JS_URL = f"{BASE_URL}/js/site.js?h={JS_HASH}"
GOOD_CACHE = "public, max-age = 0, must-revalidate, no-transform"
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
        errors = production.verify(BASE_URL, 1.0, EXPECTED_REVISION)
    test.assertEqual(responses, {}, f"required URLs were not requested: {responses!r}")
    test.assertEqual(len(calls), 6)
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
        self.assertIn("must not be immutable", errors[0])

    def test_non_200_authored_asset_fails(self) -> None:
        errors = run_production_fixture(self, js_status=404, js_body=b"not found")
        self.assertEqual(len(errors), 1, errors)
        self.assertIn(f"{JS_URL!r} returned 404, expected 200", errors[0])

    def test_revision_cache_policy_rejects_immutable(self) -> None:
        errors = run_production_fixture(
            self, revision_cache="NO-STORE, NO-TRANSFORM, IMMUTABLE"
        )
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("/build-revision.txt Cache-Control must not be immutable", errors[0])

    def test_missing_malformed_and_external_asset_hashes_fail(self) -> None:
        errors: list[str] = []
        body = (
            '<link rel="stylesheet" href="/css/missing.css">'
            '<script src="/js/bad.js?h=ABC"></script>'
            '<script src="https://example.com/app.js?h=11111111111111111111"></script>'
        )
        assets = production.collect_hashed_assets(
            errors, f"{BASE_URL}/", f"{BASE_URL}/", body
        )
        self.assertEqual(assets, [])
        self.assertEqual(len(errors), 3, errors)
        self.assertTrue(any("exactly one h" in error for error in errors), errors)
        self.assertTrue(any("malformed h" in error for error in errors), errors)
        self.assertTrue(any("external JavaScript" in error for error in errors), errors)

    def test_page_missing_css_and_javascript_references_fails(self) -> None:
        errors: list[str] = []
        assets = production.collect_hashed_assets(
            errors, f"{BASE_URL}/", f"{BASE_URL}/", "<main>Evidence register</main>"
        )
        self.assertEqual(assets, [])
        self.assertEqual(len(errors), 2, errors)
        self.assertTrue(any("no authored CSS" in error for error in errors), errors)
        self.assertTrue(any("no authored JavaScript" in error for error in errors), errors)

    def test_conflicting_hashes_for_one_asset_path_fail(self) -> None:
        other_hash = "1" * 20
        other_url = f"{BASE_URL}/js/site.js?h={other_hash}"
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

    def test_duplicate_live_max_age_values_fail(self) -> None:
        errors: list[str] = []
        production.validate_revalidating_cache(
            errors,
            "/",
            {
                "Cache-Control": (
                    "PUBLIC, MAX-AGE = 0, MUST-REVALIDATE, NO-TRANSFORM, max-age=31536000"
                )
            },
        )
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("exactly one max-age value", errors[0])


class CacheContractTests(unittest.TestCase):
    def test_overlapping_cache_values_are_rejected(self) -> None:
        headers = """/*
  Cache-Control: public, max-age=0, must-revalidate, no-transform
/css/*
  Cache-Control: public, max-age=60, no-transform
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
  Cache-Control: public, max-age=0, must-revalidate, no-transform
/img/*
  ! Cache-Control
  Cache-Control: public, max-age=31536000, immutable, no-transform
/build-revision.txt
  ! Cache-Control
  Cache-Control: no-store, no-transform
"""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            output.joinpath("img").mkdir()
            output.joinpath("img/art.png").write_bytes(b"png")
            errors: list[str] = []
            site.validate_cache_contract(errors, output, headers)
        self.assertTrue(any("must not be immutable" in error for error in errors), errors)

    def test_revision_sentinel_must_be_no_store(self) -> None:
        headers = """/*
  Cache-Control: public, max-age=0, must-revalidate, no-transform
/build-revision.txt
  ! Cache-Control
  Cache-Control: public, max-age=60, no-transform
"""
        with tempfile.TemporaryDirectory() as directory:
            errors: list[str] = []
            site.validate_cache_contract(errors, Path(directory), headers)
        self.assertTrue(any("must have exactly" in error for error in errors), errors)


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
            for path in (system_page, catalog_page, evidence_page, cast_file):
                path.parent.mkdir(parents=True, exist_ok=True)
            cast_file.write_text("{}\n")
            cast = "/casts/demo.cast"
            system_markup = (
                f'<div data-cast="{cast}"></div>'
                '<link href="/vendor/asciinema/asciinema-player.css">'
                '<script src="/vendor/asciinema/asciinema-player.min.js"></script>'
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
            site.validate_player_contract(
                errors,
                [(Path("content/systems/demo.md"), cast)],
                html,
                "script-src 'self' 'wasm-unsafe-eval'",
                output,
                static,
            )
            self.assertEqual(errors, [])

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


if __name__ == "__main__":
    unittest.main()
