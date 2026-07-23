"""Focused regressions for release identity, cache, tape, and player contracts."""

from __future__ import annotations

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


class RevisionContractTests(unittest.TestCase):
    def test_older_well_formed_artifact_fails_expected_revision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            output.joinpath("build-revision.txt").write_text("1" * 40 + "\n")
            errors: list[str] = []
            site.validate_revision(errors, output, "2" * 40)
            self.assertTrue(any("mismatch" in error for error in errors), errors)

    def test_live_verifier_rejects_older_compatible_deployment(self) -> None:
        old = "1" * 40
        expected = "2" * 40

        def response(url: str, _timeout: float, follow: bool = True):
            if url.endswith("build-revision.txt"):
                return 200, {"Cache-Control": "no-store, no-transform"}, f"{old}\n".encode()
            if url.endswith("evidence/"):
                body = (
                    '<link rel="canonical" href="https://ardent.tools/evidence/">'
                    "Evidence register 0 published casts."
                ).encode()
                headers = {
                    "Cache-Control": "public, max-age=0, must-revalidate, no-transform",
                    "Content-Security-Policy": "script-src 'self'",
                }
                return 200, headers, body
            if url.endswith("demos/") and not follow:
                return 301, {"Location": "/evidence/"}, b""
            raise AssertionError(url)

        with mock.patch.object(production, "request", side_effect=response):
            errors = production.verify("https://ardent.tools", 1.0, expected)
        self.assertTrue(any("deployed revision mismatch" in error for error in errors), errors)


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
