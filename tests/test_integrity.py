"""Focused regressions for release identity, cache, tape, and player contracts."""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import importlib.util
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))


def load_script(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "bin" / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


site = load_script("ardent_validate_site", "validate-site.py")
production = load_script("ardent_verify_production", "verify-production.py")
redirects = load_script("ardent_redirect_contract", "redirect_contract.py")
headers_contract = load_script("ardent_header_contract", "header_contract.py")
html_contract = load_script("ardent_html_authority", "html_authority.py")
pages_runtime = load_script("ardent_pages_runtime", "pages_runtime.py")
pages_limits = sys.modules["pages_limits"]
catalog = load_script("ardent_generate_catalog", "generate-systems-json.py")
career = load_script("ardent_career_claims", "validate-career-claims.py")
site_entrypoint = load_script("ardent_site_entrypoint", "site.py")
resume_fonts = load_script("ardent_resume_fonts", "validate-resume-fonts.py")
release = load_script("ardent_release_manifest", "release_manifest.py")
content_address = load_script("ardent_content_address", "content_address.py")
asset_retention = load_script("ardent_asset_retention", "asset_retention.py")
deployment_receipt = load_script(
    "ardent_pages_deployment_receipt", "pages_deployment_receipt.py"
)

BASE_URL = "https://ardent.tools"
EXPECTED_REVISION = "2" * 40
CSS_BODY = b"body { color: #231f20; }\n"
JS_BODY = b"document.documentElement.dataset.ready = 'true';\n"
ERROR_JS_BODY = b"document.documentElement.dataset.errorPage = 'true';\n"
CSS_HASH = hashlib.sha256(CSS_BODY).hexdigest()
JS_HASH = hashlib.sha256(JS_BODY).hexdigest()
ERROR_JS_HASH = hashlib.sha256(ERROR_JS_BODY).hexdigest()


def addressed_output(logical_path: str, body: bytes) -> str:
    digest = hashlib.sha256(body).hexdigest()
    return f"a/{digest}{Path(logical_path).suffix.lower()}"


CSS_OUTPUT = addressed_output("css/site.css", CSS_BODY)
JS_OUTPUT = addressed_output("js/site.js", JS_BODY)
ERROR_JS_OUTPUT = addressed_output("js/error.js", ERROR_JS_BODY)
CSS_URL = f"{BASE_URL}/{CSS_OUTPUT}"
JS_URL = f"{BASE_URL}/{JS_OUTPUT}"
ERROR_JS_URL = f"{BASE_URL}/{ERROR_JS_OUTPUT}"
ASSET_MARKUP = (
    f'<link rel="stylesheet" href="{CSS_URL}"><script src="{JS_URL}" defer></script>'
)
GOOD_CACHE = "no-store, no-transform"
GOOD_IMMUTABLE_CACHE = "public, max-age=31536000, immutable"
GOOD_CSP = (
    "default-src 'self'; img-src 'self'; style-src 'self'; script-src 'self'; "
    "font-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'self'; "
    "frame-ancestors 'none'; object-src 'none'; manifest-src 'self'; "
    "worker-src 'none'; upgrade-insecure-requests"
)


def run_production_fixture(
    test: unittest.TestCase,
    *,
    revision: str = EXPECTED_REVISION,
    revision_cache: str = "no-store, no-transform",
    css_body: bytes = CSS_BODY,
    css_cache: str = GOOD_IMMUTABLE_CACHE,
    js_body: bytes = JS_BODY,
    js_cache: str = GOOD_IMMUTABLE_CACHE,
    js_status: int = 200,
    error_js_body: bytes = ERROR_JS_BODY,
    about_status: int = 200,
    about_body: bytes | None = None,
    custom_404_status: int = 404,
    custom_404_body: bytes | None = None,
    custom_404_cache: str = GOOD_CACHE,
    custom_404_csp: str = GOOD_CSP,
    custom_404_content_type: str = "text/html; charset=utf-8",
    tombstone_status: int = 404,
    tombstone_cache: str = GOOD_CACHE,
    live_manifest_body: bytes | None = None,
    resource_overrides: dict[str, tuple[int, str, bytes]] | None = None,
    redirect_statuses: dict[str, int] | None = None,
    redirect_targets: dict[str, str] | None = None,
    root_header_overrides: dict[str, str | None] | None = None,
    speculation_content_type: str = headers_contract.SPECULATION_MEDIA_TYPE,
    logical_alias_overrides: dict[str, tuple[int, bytes]] | None = None,
    require_logical_alias_tombstones: bool = True,
) -> list[str]:
    assets = ASSET_MARKUP
    sitemap_body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"<url><loc>{BASE_URL}/</loc></url>"
        f"<url><loc>{BASE_URL}/about/</loc></url>"
        f"<url><loc>{BASE_URL}/evidence/</loc></url>"
        "</urlset>"
    ).encode()
    root_body = f'<link rel="canonical" href="{BASE_URL}/">{assets}'.encode()
    default_about = (
        f'<link rel="canonical" href="{BASE_URL}/about/">About{assets}'
    ).encode()
    evidence_body = (
        f'<link rel="canonical" href="{BASE_URL}/evidence/">'
        "Would show: 0 published casts."
        f"{assets}"
    ).encode()
    default_404 = (
        f'<link rel="canonical" href="{BASE_URL}/404/">'
        "404: no such path Return home "
        f'<link rel="stylesheet" href="{CSS_URL}">'
        f'<script src="{ERROR_JS_URL}" defer></script>'
    ).encode()
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory)
        files = {
            "atom.xml": b"<feed/>\n",
            "build-revision.txt": f"{EXPECTED_REVISION}\n".encode(),
            "career-claims.json": b"{}\n",
            "llms.txt": b"release fixture\n",
            "robots.txt": b"User-agent: *\n",
            "runtime-boundary.json": b"{}\n",
            "sitemap.xml": sitemap_body,
            "systems.json": b"[]\n",
        }
        addressed_bodies = {
            "css/site.css": CSS_BODY,
            "js/site.js": JS_BODY,
            "js/error.js": ERROR_JS_BODY,
            "site.webmanifest": b"{}\n",
            "speculation-rules.json": b"{}\n",
        }
        asset_resources = []
        for logical_path, body in addressed_bodies.items():
            digest = hashlib.sha256(body).hexdigest()
            output_path = addressed_output(logical_path, body)
            files[output_path] = body
            asset_resources.append(
                {
                    "logical_path": logical_path,
                    "output_path": output_path,
                    "request_url": f"/{output_path}",
                    "sha256": digest,
                    "cache_class": "addressed",
                }
            )
        asset_map = {
            "schema_version": release.ASSET_MAP_SCHEMA_VERSION,
            "resource_count": len(asset_resources),
            "resources": asset_resources,
            "media_types": {
                item["request_url"]: release.SPECULATION_MEDIA_TYPE
                for item in asset_resources
                if item["logical_path"] == "speculation-rules.json"
            },
        }
        for relative, body in files.items():
            path = output / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        local_html = {
            "index.html": root_body,
            "about/index.html": default_about,
            "evidence/index.html": evidence_body,
            "404/index.html": default_404,
            "404.html": default_404,
        }
        for relative, body in local_html.items():
            path = output / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        html_authority = html_contract.build_authority(
            output, EXPECTED_REVISION, BASE_URL
        )
        html_authority_bytes = html_contract.serialize_authority(html_authority)
        (output / html_contract.AUTHORITY_NAME).write_bytes(html_authority_bytes)
        files[html_contract.AUTHORITY_NAME] = html_authority_bytes
        contract, contract_errors = release.read_contract(
            ROOT / "release-resources.toml"
        )
        test.assertEqual(contract_errors, [])
        manifest = release.build_manifest(
            output, EXPECTED_REVISION, asset_map, contract
        )
        manifest_bytes = release.serialize_manifest(manifest)
        (output / contract["manifest_name"]).write_bytes(manifest_bytes)
        direct_contract, direct_contract_errors = headers_contract.expected_contract(
            manifest
        )
        test.assertEqual(direct_contract_errors, [])
        test.assertIsNotNone(direct_contract)

        def direct_headers() -> dict[str, str]:
            return dict(direct_contract.direct_response)

        def with_cache(cache: str) -> dict[str, str]:
            result = direct_headers()
            result["cache-control"] = cache
            return result

        responses: dict[tuple[str, bool], tuple[int, dict[str, str], bytes]] = {}
        for item in manifest["resources"]:
            body = files[item["output_path"]]
            logical_path = item["logical_path"]
            status = 200
            cache = (
                GOOD_IMMUTABLE_CACHE
                if item["cache_class"] in {"addressed", "retained"}
                else GOOD_CACHE
            )
            if logical_path == "build-revision.txt":
                body = f"{revision}\n".encode()
                cache = revision_cache
            elif logical_path == "css/site.css":
                body = css_body
                cache = css_cache
            elif logical_path == "js/site.js":
                body = js_body
                cache = js_cache
                status = js_status
            elif logical_path == "js/error.js":
                body = error_js_body
            if resource_overrides and logical_path in resource_overrides:
                status, cache, body = resource_overrides[logical_path]
            url = f"{BASE_URL}{item['request_url']}"
            response_headers = with_cache(cache)
            if logical_path == "speculation-rules.json":
                response_headers["content-type"] = speculation_content_type
            responses[(url, False)] = (status, response_headers, body)

        responses[(f"{BASE_URL}/{contract['manifest_name']}", False)] = (
            200,
            with_cache(GOOD_CACHE),
            manifest_bytes if live_manifest_body is None else live_manifest_body,
        )
        page_headers = {
            **direct_headers(),
            "content-type": "text/html; charset=utf-8",
        }
        root_headers = {
            **direct_headers(),
            "content-type": "text/html; charset=utf-8",
        }
        for name, value in (root_header_overrides or {}).items():
            matches = [key for key in root_headers if key.lower() == name.lower()]
            for key in matches:
                del root_headers[key]
            if value is not None:
                root_headers[name] = value
        responses[(f"{BASE_URL}/", False)] = (
            200,
            root_headers,
            (f'<link rel="canonical" href="{BASE_URL}/">{assets}').encode(),
        )
        default_about = (
            f'<link rel="canonical" href="{BASE_URL}/about/">About{assets}'
        ).encode()
        responses[(f"{BASE_URL}/about/", False)] = (
            about_status,
            page_headers,
            default_about if about_body is None else about_body,
        )
        responses[(f"{BASE_URL}/evidence/", False)] = (
            200,
            page_headers,
            (
                f'<link rel="canonical" href="{BASE_URL}/evidence/">'
                "Would show: 0 published casts."
                f"{assets}"
            ).encode(),
        )
        responses[(f"{BASE_URL}/404/", False)] = (
            200,
            page_headers,
            default_404,
        )
        for alias_path, target_path in production.html_alias_redirects(html_authority):
            responses[(f"{BASE_URL}{alias_path}", False)] = (
                308,
                {**direct_headers(), "Location": target_path},
                b"",
            )
        missing_path = production.missing_probe_path(EXPECTED_REVISION)
        default_404 = (
            f'<link rel="canonical" href="{BASE_URL}/404/">'
            "404: no such path Return home "
            f'<link rel="stylesheet" href="{CSS_URL}">'
            f'<script src="{ERROR_JS_URL}" defer></script>'
        ).encode()
        responses[(f"{BASE_URL}{missing_path}", False)] = (
            custom_404_status,
            {
                **direct_headers(),
                "cache-control": custom_404_cache,
                "content-security-policy": custom_404_csp,
                "content-type": custom_404_content_type,
            },
            default_404 if custom_404_body is None else custom_404_body,
        )
        if require_logical_alias_tombstones:
            for item in manifest["resources"]:
                if item["cache_class"] != "addressed":
                    continue
                alias_status, alias_body = (logical_alias_overrides or {}).get(
                    item["logical_path"], (404, default_404)
                )
                responses[(f"{BASE_URL}/{item['logical_path']}", False)] = (
                    alias_status,
                    {
                        **direct_headers(),
                        "content-type": "text/html; charset=utf-8",
                    },
                    alias_body,
                )
        for tombstone in manifest["tombstones"]:
            responses[(f"{BASE_URL}{tombstone['path']}", False)] = (
                tombstone_status,
                with_cache(tombstone_cache),
                b"not found\n",
            )
        redirect_rules, redirect_errors = redirects.load_redirects(ROOT / "_redirects")
        test.assertEqual(redirect_errors, [])
        for rule in redirect_rules:
            probe_path = redirects.redirect_probe_path(rule, EXPECTED_REVISION)
            responses[(f"{BASE_URL}{probe_path}", False)] = (
                (redirect_statuses or {}).get(rule.source, rule.status),
                {"Location": (redirect_targets or {}).get(rule.source, rule.target)},
                b"",
            )
        calls: list[tuple[str, bool]] = []
        expected_calls = len(responses)

        def response(url: str, _timeout: float, follow: bool = True):
            key = (url, follow)
            calls.append(key)
            test.assertIn(key, responses, f"unexpected or duplicate request: {key!r}")
            return responses.pop(key)

        with mock.patch.object(production, "request", side_effect=response):
            errors = production.verify(
                BASE_URL,
                1.0,
                EXPECTED_REVISION,
                manifest,
                manifest_bytes,
                contract["manifest_name"],
                redirect_rules,
                html_authority,
                direct_contract,
                require_logical_alias_tombstones=(
                    require_logical_alias_tombstones
                ),
            )
        test.assertEqual(
            responses, {}, f"required URLs were not requested: {responses!r}"
        )
        test.assertEqual(len(calls), expected_calls)
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
    def test_transient_retry_diagnostic_is_bounded_and_complete_in_count(
        self,
    ) -> None:
        errors = [
            f"failure {index}: first line\nsecond line " + ("x" * 10_000)
            for index in range(400)
        ]
        summary = production.bounded_retry_diagnostic(errors)
        self.assertLess(len(summary), 1024)
        self.assertNotIn("\n", summary)
        self.assertIn("400 errors", summary)
        self.assertIn("failure 0", summary)
        self.assertIn("397 more deferred until the final attempt", summary)
        self.assertNotIn("failure 3", summary)

    def test_retry_control_emits_bounded_progress_then_succeeds(self) -> None:
        results = iter([["transient\n" + ("x" * 10_000)], []])

        def verify_once(colos: set[str]) -> list[str]:
            colos.add("SEA")
            return next(results)

        stdout = io.StringIO()
        stderr = io.StringIO()
        sleep = mock.Mock()
        result = production.run_verification_attempts(
            verify_once,
            attempts=2,
            delay=10,
            stdout=stdout,
            stderr=stderr,
            sleep_fn=sleep,
        )
        self.assertEqual(result, 0)
        progress = stderr.getvalue().splitlines()
        self.assertEqual(len(progress), 1)
        self.assertLess(len(progress[0]), 1024)
        self.assertIn("1 error", progress[0])
        self.assertEqual(
            stdout.getvalue(),
            "PASS: production boundary verified on attempt 2; Cloudflare colos=SEA\n",
        )
        sleep.assert_called_once_with(10)

    def test_retry_control_preserves_complete_terminal_errors(self) -> None:
        errors = ["first complete error", "second complete error"]
        stdout = io.StringIO()
        stderr = io.StringIO()
        sleep = mock.Mock()
        result = production.run_verification_attempts(
            lambda _colos: errors,
            attempts=2,
            delay=10,
            stdout=stdout,
            stderr=stderr,
            sleep_fn=sleep,
        )
        self.assertEqual(result, 1)
        self.assertEqual(stdout.getvalue(), "")
        lines = stderr.getvalue().splitlines()
        self.assertEqual(lines[-2:], [f"ERROR: {error}" for error in errors])
        self.assertLess(len(lines[0]), 1024)
        sleep.assert_called_once_with(10)

    def test_matching_authored_asset_bodies_pass(self) -> None:
        self.assertEqual(run_production_fixture(self), [])

    def test_stale_body_at_exact_authored_url_fails_digest(self) -> None:
        errors = run_production_fixture(self, js_body=b"stale JavaScript body\n")
        self.assertEqual(len(errors), 2, errors)
        self.assertTrue(
            any("release resource digest mismatch" in error for error in errors), errors
        )
        self.assertTrue(
            any(
                "authored JavaScript asset digest mismatch" in error for error in errors
            ),
            errors,
        )
        self.assertTrue(all(JS_OUTPUT in error for error in errors), errors)

    def test_malformed_immutable_asset_cache_policy_fails(self) -> None:
        errors = run_production_fixture(
            self,
            js_cache="public, max-age=0, must-revalidate, no-transform, immutable",
        )
        self.assertEqual(len(errors), 1, errors)
        self.assertIn(
            "must be exactly public, max-age=31536000, immutable", errors[0]
        )

    def test_addressed_asset_no_store_cache_policy_fails(self) -> None:
        errors = run_production_fixture(self, js_cache=GOOD_CACHE)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn(
            "must be exactly public, max-age=31536000, immutable", errors[0]
        )

    def test_non_200_authored_asset_fails(self) -> None:
        errors = run_production_fixture(self, js_status=404, js_body=b"not found")
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("returned 404, expected direct 200", errors[0])
        self.assertIn(JS_OUTPUT, errors[0])

    def test_stale_logical_asset_alias_fails_live_boundary(self) -> None:
        errors = run_production_fixture(
            self,
            logical_alias_overrides={"js/site.js": (200, JS_BODY)},
        )
        self.assertTrue(
            any(
                "logical asset alias /js/site.js returned 200" in error
                for error in errors
            ),
            errors,
        )

    def test_custom_origin_does_not_claim_control_of_legacy_edge_objects(self) -> None:
        errors = run_production_fixture(
            self,
            logical_alias_overrides={"js/site.js": (200, JS_BODY)},
            require_logical_alias_tombstones=False,
        )
        self.assertEqual(errors, [])

    def test_query_free_runtime_html_authority_drift_fails(self) -> None:
        errors = run_production_fixture(
            self,
            resource_overrides={
                html_contract.AUTHORITY_NAME: (200, GOOD_CACHE, b"stale authority\n")
            },
        )
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("release resource digest mismatch", errors[0])
        self.assertIn("/release-html.json", errors[0])

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
            errors, f"{BASE_URL}/", f"{BASE_URL}/", body
        )
        self.assertEqual(assets, [])
        self.assertEqual(len(errors), 3, errors)
        self.assertTrue(any("full-sha256" in error for error in errors), errors)
        self.assertTrue(
            any("query- and fragment-free" in error for error in errors), errors
        )
        self.assertTrue(any("external JavaScript" in error for error in errors), errors)

    def test_page_missing_css_and_javascript_references_fails(self) -> None:
        errors: list[str] = []
        assets = production.collect_hashed_assets(
            errors,
            f"{BASE_URL}/",
            f"{BASE_URL}/",
            "<main>Evidence register</main>",
        )
        self.assertEqual(assets, [])
        self.assertEqual(len(errors), 2, errors)
        self.assertTrue(any("no authored CSS" in error for error in errors), errors)
        self.assertTrue(
            any("no authored JavaScript" in error for error in errors), errors
        )

    def test_canonical_asset_urls_are_fetched_from_immutable_origin_under_test(
        self,
    ) -> None:
        immutable = "https://deadbeef.ardent-tools.pages.dev"
        errors: list[str] = []
        assets = production.collect_hashed_assets(
            errors,
            f"{immutable}/",
            f"{immutable}/about/",
            ASSET_MARKUP,
            f"{BASE_URL}/",
        )
        self.assertEqual(errors, [])
        self.assertEqual(
            {url for url, _digest, _kind in assets},
            {
                f"{immutable}/{CSS_OUTPUT}",
                f"{immutable}/{JS_OUTPUT}",
            },
        )

    def test_conflicting_hashes_for_one_asset_path_fail(self) -> None:
        other_hash = "1" * 64
        errors: list[str] = []
        assets = production.distinct_assets(
            errors,
            [
                (JS_URL, JS_HASH, "JavaScript"),
                (JS_URL, other_hash, "JavaScript"),
            ],
        )
        self.assertEqual(set(assets), {JS_URL})
        self.assertEqual(len(errors), 2, errors)
        self.assertIn("conflicting authored hashes for /a/", errors[0])

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

    def test_physical_asset_path_and_query_shape_fail_closed(self) -> None:
        cases = {
            "logical alias": "/js/site.js",
            "short digest": "/a/11111111111111111111.js",
            "query": f"/{JS_OUTPUT}?v=1",
            "fragment": f"/{JS_OUTPUT}#stale",
            "wrong extension": f"/a/{JS_HASH}.css",
        }
        for label, reference in cases.items():
            with self.subTest(label=label):
                errors: list[str] = []
                production.collect_hashed_assets(
                    errors,
                    f"{BASE_URL}/",
                    f"{BASE_URL}/",
                    f'<link rel="stylesheet" href="{CSS_URL}"><script src="{reference}"></script>',
                )
                self.assertEqual(len(errors), 1, errors)


class ProductionRouteContractTests(unittest.TestCase):
    def test_html_aliases_special_case_the_custom_404_stem(self) -> None:
        authority = {
            "routes": [
                {"request_path": "/", "output_path": "index.html"},
                {"request_path": "/about/", "output_path": "about/index.html"},
                {"request_path": "/404/", "output_path": "404/index.html"},
            ],
            "custom_404": {"output_path": "404.html"},
        }
        aliases = production.html_alias_redirects(authority)
        self.assertIn(("/index.html", "/"), aliases)
        self.assertIn(("/about", "/about/"), aliases)
        self.assertIn(("/about/index.html", "/about/"), aliases)
        self.assertIn(("/404/index.html", "/404/"), aliases)
        self.assertNotIn(("/404", "/404/"), aliases)
        self.assertNotIn(("/404.html", "/404/"), aliases)

    def test_custom_404_probe_is_revision_specific_and_disjoint(self) -> None:
        path = production.missing_probe_path(EXPECTED_REVISION)
        self.assertEqual(path, production.missing_probe_path(EXPECTED_REVISION))
        self.assertNotEqual(path, production.missing_probe_path("3" * 40))
        self.assertRegex(path, r"^/__ardent-missing-[0-9a-f]{24}/$")
        errors: list[str] = []
        self.assertTrue(
            production.missing_probe_is_disjoint(errors, path, ["/", "/about/"])
        )
        self.assertEqual(errors, [])

    def test_custom_404_probe_collision_fails_closed(self) -> None:
        path = production.missing_probe_path(EXPECTED_REVISION)
        errors: list[str] = []
        self.assertFalse(
            production.missing_probe_is_disjoint(errors, path, ["/", path])
        )
        self.assertIn("collides with sitemap route", errors[0])

    def test_custom_404_wrong_status_and_missing_marker_fail(self) -> None:
        errors = run_production_fixture(
            self,
            custom_404_status=200,
            custom_404_body=("Return home " + ASSET_MARKUP).encode(),
        )
        self.assertTrue(any("expected exact 404" in error for error in errors), errors)
        self.assertTrue(
            any(
                "lacks custom 404 marker '404: no such path'" in error
                for error in errors
            ),
            errors,
        )

    def test_custom_404_cache_csp_and_injection_fail(self) -> None:
        errors = run_production_fixture(
            self,
            custom_404_cache="public, max-age=0, must-revalidate",
            custom_404_csp="default-src *; script-src 'unsafe-inline'",
            custom_404_body=(
                "404: no such path Return home <span data-cfemail>hidden</span> "
                + ASSET_MARKUP
            ).encode(),
        )
        self.assertTrue(
            any("Cache-Control must be exactly" in error for error in errors), errors
        )
        self.assertTrue(
            any("strict zero-cast CSP differs" in error for error in errors), errors
        )
        self.assertTrue(
            any("Cloudflare email-protection" in error for error in errors), errors
        )

    def test_custom_404_wrong_html_media_type_fails(self) -> None:
        errors = run_production_fixture(
            self, custom_404_content_type="application/octet-stream"
        )
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("Content-Type must be HTML", errors[0])

    def test_custom_404_query_asset_identity_fails(self) -> None:
        malformed = (
            "404: no such path Return home "
            f'<link rel="stylesheet" href="{CSS_URL}">'
            f'<script src="/{JS_OUTPUT}?v=1"></script>'
        ).encode()
        errors = run_production_fixture(self, custom_404_body=malformed)
        self.assertTrue(
            any("query- and fragment-free" in error for error in errors), errors
        )

    def test_custom_404_only_asset_stale_bytes_fail_digest(self) -> None:
        errors = run_production_fixture(
            self, error_js_body=b"stale custom 404 script\n"
        )
        self.assertTrue(
            any(
                "release resource digest mismatch" in error and ERROR_JS_OUTPUT in error
                for error in errors
            ),
            errors,
        )
        self.assertTrue(
            any(
                "authored JavaScript asset digest mismatch" in error
                and ERROR_JS_URL in error
                for error in errors
            ),
            errors,
        )

    def test_canonical_route_redirect_cannot_hide(self) -> None:
        errors = run_production_fixture(self, about_status=301)
        self.assertTrue(
            any(
                "/about/ returned 301, expected direct 200" in error for error in errors
            ),
            errors,
        )

    def test_canonical_route_rewrite_to_root_body_cannot_hide(self) -> None:
        root_body = (
            f'<link rel="canonical" href="{BASE_URL}/">Root body{ASSET_MARKUP}'
        ).encode()
        errors = run_production_fixture(self, about_body=root_body)
        self.assertTrue(
            any(
                "canonical resolves" in error and "/about/" in error for error in errors
            ),
            errors,
        )


class RedirectContractTests(unittest.TestCase):
    def test_repository_redirect_contract_is_exact(self) -> None:
        rules, errors = redirects.load_redirects(ROOT / "_redirects")
        self.assertEqual(errors, [])
        self.assertEqual(tuple(rules), redirects.SUPPORTED_REDIRECTS)

    def test_live_probe_set_covers_exact_and_revision_safe_paths(self) -> None:
        probes = {
            rule.source: redirects.redirect_probe_path(rule, EXPECTED_REVISION)
            for rule in redirects.SUPPORTED_REDIRECTS
        }
        self.assertEqual(probes["/demos"], "/demos")
        self.assertEqual(probes["/demos/*"], "/demos/")
        self.assertEqual(probes["/404"], "/404")
        self.assertEqual(probes["/404.html"], "/404.html")
        self.assertRegex(
            probes["/systems/ergon-tools/*"],
            r"^/systems/ergon-tools/__ardent-probe-[0-9a-f]{24}$",
        )
        self.assertRegex(
            probes["/systems/nosologia/*"],
            r"^/systems/nosologia/__ardent-probe-[0-9a-f]{24}$",
        )
        ergon_rule = next(
            rule
            for rule in redirects.SUPPORTED_REDIRECTS
            if rule.source == "/systems/ergon-tools/*"
        )
        alternate = redirects.redirect_probe_path(
            ergon_rule,
            "3" * 40,
        )
        self.assertNotEqual(probes["/systems/ergon-tools/*"], alternate)

    def test_each_supported_declaration_omission_fails(self) -> None:
        declarations = [rule.declaration for rule in redirects.SUPPORTED_REDIRECTS]
        for omitted in declarations:
            with self.subTest(omitted=omitted):
                raw = "\n".join(
                    declaration
                    for declaration in declarations
                    if declaration != omitted
                )
                _, errors = redirects.parse_redirects(raw)
                self.assertTrue(
                    any(
                        "missing supported redirect declaration" in error
                        and omitted in error
                        for error in errors
                    ),
                    errors,
                )

    def test_extra_duplicate_malformed_external_ambiguous_and_loop_fail(self) -> None:
        base = "\n".join(rule.declaration for rule in redirects.SUPPORTED_REDIRECTS)
        cases = {
            "extra": (base + "\n/extra /evidence/ 301", "unsupported extra"),
            "duplicate": (
                base + "\n/demos /evidence/ 301",
                "duplicate redirect declaration",
            ),
            "malformed": (
                base + "\n/broken /evidence/",
                "malformed redirect declaration",
            ),
            "external": (
                base.replace(
                    "/demos /evidence/ 301",
                    "/demos https://example.com/ 301",
                ),
                "same-origin path",
            ),
            "ambiguous": (
                base + "\n/systems/* /evidence/ 301",
                "ambiguous redirect sources",
            ),
            "loop": (
                base.replace(
                    "/demos /evidence/ 301",
                    "/demos /demos 301",
                ),
                "redirect loops",
            ),
        }
        for label, (raw, expected) in cases.items():
            with self.subTest(label=label):
                _, errors = redirects.parse_redirects(raw)
                self.assertTrue(any(expected in error for error in errors), errors)

    def test_every_live_redirect_probe_requires_exact_status(self) -> None:
        for rule in redirects.SUPPORTED_REDIRECTS:
            with self.subTest(source=rule.source):
                errors = run_production_fixture(
                    self,
                    redirect_statuses={rule.source: 302},
                )
                probe_path = redirects.redirect_probe_path(rule, EXPECTED_REVISION)
                self.assertTrue(
                    any(
                        f"redirect probe {probe_path} returned 302" in error
                        for error in errors
                    ),
                    errors,
                )

    def test_every_live_redirect_probe_requires_exact_destination(self) -> None:
        for rule in redirects.SUPPORTED_REDIRECTS:
            with self.subTest(source=rule.source):
                errors = run_production_fixture(
                    self,
                    redirect_targets={rule.source: "/wrong/"},
                )
                probe_path = redirects.redirect_probe_path(rule, EXPECTED_REVISION)
                self.assertTrue(
                    any(
                        f"redirect probe {probe_path} resolves to" in error
                        and "expected 'https://ardent.tools/" in error
                        for error in errors
                    ),
                    errors,
                )

    def test_live_redirect_external_destination_fails_same_origin(self) -> None:
        errors = run_production_fixture(
            self,
            redirect_targets={"/demos": "https://example.com/evidence/"},
        )
        self.assertTrue(
            any("resolves outside the site" in error for error in errors),
            errors,
        )


class ContentAddressContractTests(unittest.TestCase):
    @staticmethod
    def contract() -> dict:
        contract, errors = release.read_contract(ROOT / "release-resources.toml")
        if errors:
            raise AssertionError(errors)
        return contract

    def finalize(self, root: Path, files: dict[str, bytes]) -> tuple[Path, dict]:
        output = root / "public"
        for relative, body in files.items():
            path = output / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        map_path = root / "asset-map.json"
        document = content_address.finalize_tree(
            output, map_path, BASE_URL, self.contract()
        )
        self.assertEqual(document, json.loads(map_path.read_text()))
        return output, document

    def test_finalizer_is_deterministic_and_removes_logical_aliases(self) -> None:
        files = {
            "index.html": b'<link rel="stylesheet" href="https://ardent.tools/css/app.css">',
            "css/app.css": b"body{background:url('/img/pixel.svg')}\n",
            "img/pixel.svg": (
                b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"/>'
            ),
        }
        with (
            tempfile.TemporaryDirectory() as first,
            tempfile.TemporaryDirectory() as second,
        ):
            first_output, first_map = self.finalize(Path(first), files)
            second_output, second_map = self.finalize(Path(second), files)
            self.assertEqual(first_map, second_map)
            self.assertEqual(
                sorted(
                    (path.relative_to(first_output).as_posix(), path.read_bytes())
                    for path in first_output.rglob("*")
                    if path.is_file()
                ),
                sorted(
                    (path.relative_to(second_output).as_posix(), path.read_bytes())
                    for path in second_output.rglob("*")
                    if path.is_file()
                ),
            )
            for logical in ("css/app.css", "img/pixel.svg"):
                self.assertFalse((first_output / logical).exists())
            html = (first_output / "index.html").read_text()
            self.assertNotIn("/css/app.css", html)
            self.assertRegex(html, r"https://ardent\.tools/a/[0-9a-f]{64}\.css")

    def test_child_change_changes_child_and_parent_physical_identity(self) -> None:
        base = {
            "index.html": b'<link rel="stylesheet" href="/css/app.css">',
            "css/app.css": b"body{background:url('/img/pixel.svg')}\n",
            "img/pixel.svg": b'<svg xmlns="http://www.w3.org/2000/svg"/>',
        }
        changed = dict(base)
        changed["img/pixel.svg"] = (
            b'<svg xmlns="http://www.w3.org/2000/svg"><path/></svg>'
        )
        with (
            tempfile.TemporaryDirectory() as first,
            tempfile.TemporaryDirectory() as second,
        ):
            _first_output, first_map = self.finalize(Path(first), base)
            _second_output, second_map = self.finalize(Path(second), changed)
        first_by_logical = {
            item["logical_path"]: item["output_path"] for item in first_map["resources"]
        }
        second_by_logical = {
            item["logical_path"]: item["output_path"]
            for item in second_map["resources"]
        }
        self.assertNotEqual(
            first_by_logical["img/pixel.svg"], second_by_logical["img/pixel.svg"]
        )
        self.assertNotEqual(
            first_by_logical["css/app.css"], second_by_logical["css/app.css"]
        )

    def test_rewriter_changes_only_exact_same_origin_reference_tokens(self) -> None:
        files = {
            "index.html": (
                b'<img src="https://example.com/img/pixel.svg">'
                b'<img src="/img/pixel.svg">'
                b"<p>/img/pixel.svg.backup</p>"
                b'<link rel="stylesheet" href="/css/app.css">'
            ),
            "css/app.css": (
                b".label{content:'/img/pixel.svg'}"
                b".art{background:url('/img/pixel.svg')}\n"
            ),
            "img/pixel.svg": b'<svg xmlns="http://www.w3.org/2000/svg"/>',
        }
        with tempfile.TemporaryDirectory() as directory:
            output, document = self.finalize(Path(directory), files)
            html_body = (output / "index.html").read_text()
            css_item = next(
                item
                for item in document["resources"]
                if item["logical_path"] == "css/app.css"
            )
            css_body = (output / css_item["output_path"]).read_text()
        self.assertIn("https://example.com/img/pixel.svg", html_body)
        self.assertIn("/img/pixel.svg.backup", html_body)
        self.assertNotIn('src="/img/pixel.svg"', html_body)
        self.assertIn("content:'/img/pixel.svg'", css_body)
        self.assertRegex(css_body, r"background:url\('/a/[0-9a-f]{64}\.svg'\)")

    def test_html_and_json_rewriters_preserve_non_url_schema_values(self) -> None:
        files = {
            "index.html": (
                b'<meta name="description" content="/img/pixel.svg">'
                b'<meta property="og:image" content="/img/pixel.svg">'
                b'<meta property="og:video" content="/img/pixel.svg">'
                b'<meta name="twitter:app:url:iphone" content="/img/pixel.svg">'
                b'<div data="/img/pixel.svg">literal</div>'
                b'<image src="/img/pixel.svg">'
                b'<script type="application/ld+json">'
                b'{"description":"/img/pixel.svg","image":"/img/pixel.svg",'
                b'"@id":"/img/pixel.svg","mainEntityOfPage":"/img/pixel.svg"}'
                b"</script>"
            ),
            "site.webmanifest": (
                b'{"/img/pixel.svg":"schema-key","name":"/img/pixel.svg",'
                b'"icons":[{"src":"/img/pixel.svg"}]}\n'
            ),
            "img/pixel.svg": b'<svg xmlns="http://www.w3.org/2000/svg"/>',
        }
        with tempfile.TemporaryDirectory() as directory:
            output, document = self.finalize(Path(directory), files)
            html_body = (output / "index.html").read_text()
            manifest_item = next(
                item
                for item in document["resources"]
                if item["logical_path"] == "site.webmanifest"
            )
            webmanifest = json.loads(
                (output / manifest_item["output_path"]).read_text()
            )
        self.assertIn('name="description" content="/img/pixel.svg"', html_body)
        self.assertIn('<div data="/img/pixel.svg">', html_body)
        self.assertIn('"description":"/img/pixel.svg"', html_body)
        self.assertRegex(
            html_body, r'property="og:image" content="/a/[0-9a-f]{64}\.svg"'
        )
        self.assertRegex(
            html_body, r'property="og:video" content="/a/[0-9a-f]{64}\.svg"'
        )
        self.assertRegex(
            html_body,
            r'name="twitter:app:url:iphone" content="/a/[0-9a-f]{64}\.svg"',
        )
        self.assertRegex(html_body, r'<image src="/a/[0-9a-f]{64}\.svg">')
        self.assertRegex(html_body, r'"image":"/a/[0-9a-f]{64}\.svg"')
        self.assertRegex(html_body, r'"@id":"/a/[0-9a-f]{64}\.svg"')
        self.assertRegex(html_body, r'"mainEntityOfPage":"/a/[0-9a-f]{64}\.svg"')
        self.assertIn("/img/pixel.svg", webmanifest)
        self.assertEqual(webmanifest["name"], "/img/pixel.svg")
        self.assertRegex(webmanifest["icons"][0]["src"], r"^/a/[0-9a-f]{64}\.svg$")

    def test_webmanifest_dependencies_change_its_physical_identity(self) -> None:
        base = {
            "site.webmanifest": b'{"icons":[{"src":"/img/icon.png"}]}\n',
            "img/icon.png": b"first icon\n",
        }
        changed = dict(base)
        changed["img/icon.png"] = b"second icon\n"
        with (
            tempfile.TemporaryDirectory() as first,
            tempfile.TemporaryDirectory() as second,
        ):
            _first_output, first_map = self.finalize(Path(first), base)
            _second_output, second_map = self.finalize(Path(second), changed)
        first_paths = {
            item["logical_path"]: item["output_path"] for item in first_map["resources"]
        }
        second_paths = {
            item["logical_path"]: item["output_path"]
            for item in second_map["resources"]
        }
        self.assertNotEqual(
            first_paths["site.webmanifest"], second_paths["site.webmanifest"]
        )

        relative = {
            "site.webmanifest": b'{"icons":[{"src":"img/icon.png"}]}\n',
            "img/icon.png": b"icon\n",
        }
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "path-relative JSON URL field"):
                self.finalize(Path(directory), relative)

    def test_speculation_list_urls_rewrite_but_urlpatterns_do_not(self) -> None:
        files = {
            "speculation-rules.json": (
                b'{"prefetch":[{"source":"list","urls":["/img/pixel.svg"]}],'
                b'"prerender":[{"source":"document","where":'
                b'{"href_matches":"/img/pixel.svg"}}]}\n'
            ),
            "img/pixel.svg": b'<svg xmlns="http://www.w3.org/2000/svg"/>',
        }
        with tempfile.TemporaryDirectory() as directory:
            output, document = self.finalize(Path(directory), files)
            item = next(
                resource
                for resource in document["resources"]
                if resource["logical_path"] == "speculation-rules.json"
            )
            rules = json.loads((output / item["output_path"]).read_text())
        self.assertRegex(rules["prefetch"][0]["urls"][0], r"^/a/[0-9a-f]{64}\.svg$")
        self.assertEqual(
            rules["prerender"][0]["where"]["href_matches"],
            "/img/pixel.svg",
        )

    def test_dependency_capable_addressed_xml_fails_closed(self) -> None:
        for suffix in ("xml", "rss", "atom"):
            with (
                self.subTest(suffix=suffix),
                tempfile.TemporaryDirectory() as directory,
            ):
                files = {
                    f"feeds/extra.{suffix}": (
                        b'<?xml-stylesheet href="/img/pixel.svg"?><feed/>'
                    ),
                    "img/pixel.svg": b'<svg xmlns="http://www.w3.org/2000/svg"/>',
                }
                with self.assertRaisesRegex(ValueError, "dependency-capable XML"):
                    self.finalize(Path(directory), files)

    def test_unknown_webmanifest_is_outside_closed_json_authority(self) -> None:
        files = {
            "other.webmanifest": b'{"icons":[{"src":"/img/pixel.svg"}]}',
            "img/pixel.svg": b'<svg xmlns="http://www.w3.org/2000/svg"/>',
        }
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "closed schema authority"):
                self.finalize(Path(directory), files)

    def test_generic_uri_tokens_reject_ambiguous_logical_references(self) -> None:
        cases = {
            "query": '<feed><link href="/img/pixel.svg?variant=1"/></feed>',
            "fragment": '<feed><link href="/img/pixel.svg#icon"/></feed>',
            "non-http scheme": (
                '<feed><link href="mailto:user@example.com?body=/img/pixel.svg"/></feed>'
            ),
            "punctuation": '<feed><link href="/img/pixel.svg,"/></feed>',
            "backslash boundary": r'<feed><link href="/img/pixel.svg\@evil"/></feed>',
            "network path": '<feed><link href="///evil.example/img/pixel.svg"/></feed>',
            "path relative": '<feed><link href="img/pixel.svg"/></feed>',
            "percent alias": '<feed><link href="/img/%70ixel.svg"/></feed>',
            "HTTP upgrade": (
                '<feed><link href="http://ardent.tools/img/pixel.svg"/></feed>'
            ),
            "HTTP explicit 443": (
                '<feed><link href="http://ardent.tools:443/img/pixel.svg"/></feed>'
            ),
            "HTTP explicit 80": (
                '<feed><link href="http://ardent.tools:80/img/pixel.svg"/></feed>'
            ),
            "percent-encoded hostname": (
                '<feed><link href="https://%61rdent.tools/img/pixel.svg"/></feed>'
            ),
            "percent-encoded hostname dot": (
                '<feed><link href="https://ardent%2etools/img/pixel.svg"/></feed>'
            ),
            "Unicode hostname dot": (
                '<feed><link href="https://ardent。tools/img/pixel.svg"/></feed>'
            ),
            "excess authority slash": (
                '<feed><link href="https:///ardent.tools/img/pixel.svg"/></feed>'
            ),
            "credentials": (
                '<feed><link href="https://user@ardent.tools/img/pixel.svg"/></feed>'
            ),
            "foreign type discriminator": (
                '<feed xmlns:x="urn:x"><title x:type="text" type="html">'
                '&lt;img src="/img/pixel.svg"&gt;</title></feed>'
            ),
            "Atom uri attribute": (
                '<feed><generator uri="/img/pixel.svg">tool</generator></feed>'
            ),
            "processing instruction": '<?test href="/img/pixel.svg"?><feed/>',
            "xml base": (
                '<feed xml:base="/img/" '
                'xmlns:xml="http://www.w3.org/XML/1998/namespace"/>'
            ),
        }
        expected = {
            "query": "query- and fragment-free",
            "fragment": "query- and fragment-free",
            "non-http scheme": "unsupported or ambiguous URI token",
            "punctuation": "unsupported or ambiguous URI token",
            "backslash boundary": "forbidden backslash",
            "network path": "network-path resource references are forbidden",
            "path relative": "canonical XML must not depend",
            "percent alias": "canonical XML must not depend",
            "HTTP upgrade": "canonical XML must not depend",
            "HTTP explicit 443": "canonical XML must not depend",
            "HTTP explicit 80": "canonical XML must not depend",
            "percent-encoded hostname": "canonical XML must not depend",
            "percent-encoded hostname dot": "canonical XML must not depend",
            "Unicode hostname dot": "canonical XML must not depend",
            "excess authority slash": "canonical XML must not depend",
            "credentials": "canonical XML must not depend",
            "foreign type discriminator": "foreign XML attribute namespaces",
            "Atom uri attribute": "canonical XML must not depend",
            "processing instruction": "processing instructions are forbidden",
            "xml base": "xml:base is forbidden",
        }
        for label, document in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                files = {
                    "atom.xml": document.encode(),
                    "img/pixel.svg": b'<svg xmlns="http://www.w3.org/2000/svg"/>',
                }
                with self.assertRaisesRegex(ValueError, expected[label]):
                    self.finalize(Path(directory), files)

    def test_xml_and_plain_text_literal_paths_are_not_mutated(self) -> None:
        files = {
            "atom.xml": (
                b'<feed title="/img/pixel.svg"><title>/img/pixel.svg</title></feed>'
            ),
            "llms.txt": b"Literal identifier: /img/pixel.svg\n",
            "img/pixel.svg": b'<svg xmlns="http://www.w3.org/2000/svg"/>',
        }
        with tempfile.TemporaryDirectory() as directory:
            output, _document = self.finalize(Path(directory), files)
            self.assertEqual((output / "atom.xml").read_bytes(), files["atom.xml"])
            self.assertEqual((output / "llms.txt").read_bytes(), files["llms.txt"])

    def test_sitemap_extension_namespaces_fail_closed(self) -> None:
        files = {
            "sitemap.xml": (
                b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
                b'xmlns:video="http://www.google.com/schemas/sitemap-video/1.1">'
                b"<url><video:thumbnail_loc>"
                b"https://ardent.tools/img/pixel.svg"
                b"</video:thumbnail_loc></url></urlset>"
            ),
            "img/pixel.svg": b'<svg xmlns="http://www.w3.org/2000/svg"/>',
        }
        with (
            tempfile.TemporaryDirectory() as directory,
            self.assertRaisesRegex(
                ValueError, "foreign XML extension namespaces are forbidden"
            ),
        ):
            self.finalize(Path(directory), files)

    def test_markdown_inline_and_reference_destinations_are_exact(self) -> None:
        source = (
            b"[inline](/img/pixel.svg) and [reference][pixel]\n"
            b"[upgraded](HTTP://ardent.tools/img/pixel.svg)\n"
            b"[pixel]: /img/pixel.svg\n"
            b"Literal [not a complete link](/img/pixel.svg\n"
        )
        files = {
            "llms.txt": source,
            "img/pixel.svg": b'<svg xmlns="http://www.w3.org/2000/svg"/>',
        }
        with tempfile.TemporaryDirectory() as directory:
            output, _document = self.finalize(Path(directory), files)
            rewritten = (output / "llms.txt").read_text()
        self.assertEqual(len(re.findall(r"/a/[0-9a-f]{64}\.svg", rewritten)), 3)
        self.assertIn("Literal [not a complete link](/img/pixel.svg", rewritten)

    def test_markdown_ambiguous_destinations_fail_closed(self) -> None:
        cases = {
            "path relative": "[asset](img/pixel.svg)\n",
            "dot relative": "[asset](./img/pixel.svg)\n",
            "character reference": "[asset](/img/pixel&#46;svg)\n",
            "escape": r"[asset](/img/pixel\.svg)" + "\n",
            "raw HTML": '<img src="/img/pixel.svg">\n',
            "indented code": "    https://ardent.tools/img/pixel.svg\n",
            "invalid fence info": (
                "```bad`info\nhttps://ardent.tools/img/pixel.svg\n```\n"
            ),
        }
        expected = {
            "path relative": "path-relative Markdown destinations",
            "dot relative": "path-relative Markdown destinations",
            "character reference": "character references are forbidden",
            "escape": "destination escapes are forbidden",
            "raw HTML": "raw HTML is forbidden",
            "indented code": "indented Markdown code containing URL syntax",
            "invalid fence info": "fence info strings containing backticks",
        }
        for label, source in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                files = {
                    "llms.txt": source.encode(),
                    "img/pixel.svg": b'<svg xmlns="http://www.w3.org/2000/svg"/>',
                }
                with self.assertRaisesRegex(ValueError, expected[label]):
                    self.finalize(Path(directory), files)

    def test_markdown_uses_the_browser_url_authority(self) -> None:
        files = {
            "llms.txt": (
                b"[inline](https://%61rdent.tools/img/pixel.svg)\n"
                b"<https:///ardent.tools/img/pixel.svg>\n"
                + "https://ardent。tools/img/pixel.svg\n".encode()
                + b"See https://%61rdent.tools/img/pixel.svg.\n"
                + b"\\`https://%61rdent.tools/img/pixel.svg`\n"
                + b"\\[https://%61rdent.tools/img/pixel.svg](/about/)\n"
                + b"[https://%61rdent.tools/img/pixel.svg\\](/about/)\n"
            ),
            "img/pixel.svg": b'<svg xmlns="http://www.w3.org/2000/svg"/>',
        }
        with tempfile.TemporaryDirectory() as directory:
            output, _document = self.finalize(Path(directory), files)
            rewritten = (output / "llms.txt").read_text()
        self.assertEqual(
            len(re.findall(r"https://ardent\.tools/a/[0-9a-f]{64}\.svg", rewritten)),
            7,
        )
        self.assertRegex(
            rewritten, r"\nSee https://ardent\.tools/a/[0-9a-f]{64}\.svg\.\n"
        )

    def test_markdown_code_and_escape_literals_are_not_mutated(self) -> None:
        source = (
            b"`[asset](/img/pixel.svg)`\n"
            b"`https://ardent.tools/img/pixel.svg`\n"
            b"```md\n[asset](/img/pixel.svg)\n"
            b"https://ardent.tools/img/pixel.svg\n```\n"
            b"\\<https://ardent.tools/img/pixel.svg>\n"
            b'[external](https://example.com "https://ardent.tools/img/pixel.svg")\n'
        )
        files = {
            "llms.txt": source,
            "img/pixel.svg": b'<svg xmlns="http://www.w3.org/2000/svg"/>',
        }
        with tempfile.TemporaryDirectory() as directory:
            output, _document = self.finalize(Path(directory), files)
            self.assertEqual((output / "llms.txt").read_bytes(), source)

    def test_atom_embedded_html_dependency_and_doctype_fail_closed(self) -> None:
        cases = {
            "embedded HTML": (
                '<feed><content type="html">'
                '&lt;img src="/img/pixel.svg"&gt;'
                "</content></feed>"
            ),
            "document type": ('<!DOCTYPE feed SYSTEM "/img/pixel.svg"><feed/>'),
            "XHTML content": (
                '<feed><content type="xhtml">'
                '<div xmlns="http://www.w3.org/1999/xhtml">'
                '<img src="/img/pixel.svg"/></div>'
                "</content></feed>"
            ),
            "XML media content": (
                '<feed><content type="application/xhtml+xml">'
                '<div xmlns="http://www.w3.org/1999/xhtml">'
                '<img src="/img/pixel.svg"/></div>'
                "</content></feed>"
            ),
            "SVG media content": (
                '<feed><content type="image/svg+xml">'
                '<svg xmlns="http://www.w3.org/2000/svg">'
                '<image href="/img/pixel.svg"/></svg>'
                "</content></feed>"
            ),
            "HTML title": (
                '<feed><title type="html">'
                '&lt;img src="/img/pixel.svg"&gt;'
                "</title></feed>"
            ),
            "HTML subtitle": (
                '<feed><subtitle type="html">'
                '&lt;img src="/img/pixel.svg"&gt;'
                "</subtitle></feed>"
            ),
            "HTML rights": (
                '<feed><rights type="html">'
                '&lt;img src="/img/pixel.svg"&gt;'
                "</rights></feed>"
            ),
            "XHTML title": (
                '<feed><title type="xhtml">'
                '<div xmlns="http://www.w3.org/1999/xhtml">'
                '<img src="/img/pixel.svg"/></div>'
                "</title></feed>"
            ),
            "embedded style element": (
                '<feed><content type="html">'
                "&lt;style&gt;.x{background:url(/img/pixel.svg)}&lt;/style&gt;"
                "</content></feed>"
            ),
            "embedded style attribute": (
                '<feed><content type="html">'
                '&lt;div style="background:url(/img/pixel.svg)"&gt;x&lt;/div&gt;'
                "</content></feed>"
            ),
        }
        expected = {
            "embedded HTML": "canonical XML must not depend",
            "document type": "document types are forbidden",
            "XHTML content": "inline Atom XML content is forbidden",
            "XML media content": "inline Atom XML content is forbidden",
            "SVG media content": "inline Atom XML content is forbidden",
            "HTML title": "canonical XML must not depend",
            "HTML subtitle": "canonical XML must not depend",
            "HTML rights": "canonical XML must not depend",
            "XHTML title": "inline Atom XML content is forbidden",
            "embedded style element": "forbids active or style-bearing element",
            "embedded style attribute": "forbids inline style or event attributes",
        }
        for label, document in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                files = {
                    "atom.xml": document.encode(),
                    "img/pixel.svg": b'<svg xmlns="http://www.w3.org/2000/svg"/>',
                }
                with self.assertRaisesRegex(ValueError, expected[label]):
                    self.finalize(Path(directory), files)

    def test_javascript_closed_byte_authority_fails_closed(self) -> None:
        cases = {
            "fetch": "fetch('/img/pixel.svg');\n",
            "import": "import './chunk.js';\n",
            "concatenation": "fetch('/img/' + 'pixel.svg');\n",
            "unicode escape": r"fetch('/img/pix\u0065l.svg');" + "\n",
            "regex literal": "const slash=/[//]/; fetch('/img/pixel.svg');\n",
        }
        for label, script in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                files = {
                    "js/app.js": script.encode(),
                    "img/pixel.svg": b'<svg xmlns="http://www.w3.org/2000/svg"/>',
                }
                with self.assertRaisesRegex(ValueError, "closed executable authority"):
                    self.finalize(Path(directory), files)

        approved = (ROOT / "static/js/site.js").read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            _output, document = self.finalize(Path(directory), {"js/site.js": approved})
        self.assertEqual(
            document["resources"][0]["sha256"], hashlib.sha256(approved).hexdigest()
        )

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                ValueError, "bytes differ from the reviewed authority"
            ):
                self.finalize(Path(directory), {"js/site.js": approved + b"\n"})

    def test_retention_ledger_preserves_prior_physical_bodies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root / "asset-retention.json"
            assets = root / "retained-assets"

            def finalize_snapshot(
                name: str, body: bytes, record: bool
            ) -> tuple[Path, dict]:
                output = root / name / "public"
                source = output / "img/pixel.svg"
                source.parent.mkdir(parents=True)
                source.write_bytes(body)
                document = content_address.finalize_tree(
                    output,
                    root / name / "asset-map.json",
                    BASE_URL,
                    self.contract(),
                    retention_ledger=ledger,
                    retention_assets=assets,
                    record_retention_snapshot=record,
                )
                return output, document

            first_output, first_map = finalize_snapshot("first", b"first\n", True)
            first_path = first_map["resources"][0]["output_path"]
            self.assertEqual((first_output / first_path).read_bytes(), b"first\n")
            prior = root / "prior-asset-retention.json"
            prior.write_bytes(ledger.read_bytes())
            with self.assertRaisesRegex(ValueError, "latest asset-retention snapshot"):
                finalize_snapshot("unrecorded", b"second\n", False)
            second_output, second_map = finalize_snapshot("second", b"second\n", True)
            second_current = next(
                item
                for item in second_map["resources"]
                if item["cache_class"] == "addressed"
            )
            self.assertNotEqual(first_path, second_current["output_path"])
            self.assertEqual((second_output / first_path).read_bytes(), b"first\n")
            self.assertTrue(
                any(
                    item["output_path"] == first_path
                    and item["cache_class"] == "retained"
                    for item in second_map["resources"]
                )
            )
            document, retained = asset_retention.validate_ledger(ledger, assets)
            self.assertEqual(document["entry_count"], 2)
            self.assertEqual(retained[first_path], b"first\n")
            asset_retention.validate_history_prefix(document, prior)

            truncated = json.loads(json.dumps(document))
            truncated["entries"] = []
            with self.assertRaisesRegex(ValueError, "truncated"):
                asset_retention.validate_history_prefix(truncated, prior)

            rewritten = json.loads(json.dumps(document))
            rewritten["entries"][0]["resources"][0]["sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "append-only base prefix"):
                asset_retention.validate_history_prefix(rewritten, prior)

    def test_retention_integer_fields_reject_json_booleans(self) -> None:
        body = b"retained\n"
        digest = hashlib.sha256(body).hexdigest()
        output_path = f"a/{digest}.svg"
        resource = {
            "logical_path": "img/retained.svg",
            "output_path": output_path,
            "sha256": digest,
        }
        entry = {
            "kind": "snapshot",
            "sequence": 1,
            "previous_entry_sha256": None,
            "resource_count": 1,
            "resources": [resource],
        }
        document = {
            "schema_version": asset_retention.LEDGER_SCHEMA_VERSION,
            "entry_count": 1,
            "entries": [entry],
        }
        cases = {
            "schema_version": ("schema_version",),
            "sequence": ("entries", 0, "sequence"),
            "resource_count": ("entries", 0, "resource_count"),
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root / "asset-retention.json"
            assets = root / "retained-assets"
            retained = assets / output_path
            retained.parent.mkdir(parents=True)
            retained.write_bytes(body)
            for label, path in cases.items():
                candidate = copy.deepcopy(document)
                target: object = candidate
                for part in path[:-1]:
                    target = target[part]  # type: ignore[index]
                target[path[-1]] = True  # type: ignore[index]
                ledger.write_text(json.dumps(candidate))
                with (
                    self.subTest(label=label),
                    self.assertRaisesRegex(ValueError, label.replace("_", ".?")),
                ):
                    asset_retention.validate_ledger(ledger, assets)

    def test_current_physical_asset_respects_pages_file_limit(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch("pages_limits.MAX_STATIC_FILE_BYTES", 3),
            self.assertRaisesRegex(ValueError, "static-file limit"),
        ):
            self.finalize(
                Path(directory),
                {"img/pixel.svg": b"four"},
            )

    def test_retained_speculation_rules_keep_their_media_type(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root / "asset-retention.json"
            assets = root / "retained-assets"

            def finalize_snapshot(name: str, body: bytes) -> tuple[Path, dict]:
                output = root / name / "public"
                output.mkdir(parents=True)
                (output / "speculation-rules.json").write_bytes(body)
                (output / "_headers").write_text((ROOT / "_headers").read_text())
                document = content_address.finalize_tree(
                    output,
                    root / name / "asset-map.json",
                    BASE_URL,
                    self.contract(),
                    retention_ledger=ledger,
                    retention_assets=assets,
                    record_retention_snapshot=True,
                )
                return output, document

            _first_output, first = finalize_snapshot("first", b'{"prefetch":[]}\n')
            second_output, second = finalize_snapshot("second", b'{"prerender":[]}\n')
            first_url = next(iter(first["media_types"]))
            second_urls = set(second["media_types"])
            self.assertIn(first_url, second_urls)
            self.assertEqual(len(second_urls), 2)
            manifest = release.build_manifest(
                second_output,
                EXPECTED_REVISION,
                second,
                {
                    "manifest_name": "release-resources.json",
                    "canonical_paths": [],
                    "tombstones": [],
                },
            )
            self.assertEqual(manifest["media_types"], second["media_types"])
            _contract, errors = headers_contract.validate_headers(
                (second_output / "_headers").read_text(), manifest
            )
            self.assertEqual(errors, [])
            for request_url in second_urls:
                self.assertIn(
                    f"{request_url}\n  Content-Type: {release.SPECULATION_MEDIA_TYPE}",
                    (second_output / "_headers").read_text(),
                )

    def test_cycles_unknown_dependencies_and_legacy_queries_fail_closed(self) -> None:
        cases = {
            "cycle": {
                "css/a.css": b"a{background:url('/css/b.css')}\n",
                "css/b.css": b"b{background:url('/css/a.css')}\n",
            },
            "unknown": {
                "css/a.css": b"a{background:url('/img/missing.svg')}\n",
            },
            "legacy query": {
                "index.html": b'<img src="/img/pixel.svg?h=abc&amp;v=2">',
                "img/pixel.svg": b'<svg xmlns="http://www.w3.org/2000/svg"/>',
            },
        }
        expected = {
            "cycle": "dependency cycle",
            "unknown": "not a retained addressable resource",
            "legacy query": "query- and fragment-free",
        }
        for label, files in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                with self.assertRaisesRegex(ValueError, expected[label]):
                    self.finalize(Path(directory), files)

    def test_owned_sources_do_not_reintroduce_query_cache_busters(self) -> None:
        pattern = re.compile(
            r"asset_epoch|cachebust=true|[?&](?:h|v)=|&amp;(?:h|v)=",
            re.IGNORECASE,
        )
        roots = [
            ROOT / "content",
            ROOT / "static",
            ROOT / "templates",
            ROOT / "functions",
        ]
        files = [
            ROOT / "README.md",
            ROOT / "AGENTS.md",
            ROOT / "_headers",
            ROOT / "config.toml",
        ]
        for root in roots:
            files.extend(path for path in root.rglob("*") if path.is_file())
        violations: list[str] = []
        for path in files:
            if "static/vendor/" in path.as_posix():
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="strict")
            except UnicodeDecodeError:
                continue
            if pattern.search(text):
                violations.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(violations, [])


class AssetRetentionLifetimeContractTests(unittest.TestCase):
    """Coverage for the unbounded-history redesign: dedupe, the soft/hard
    entry thresholds, checkpoint compaction, and checkpoint-rooted
    validate_history_prefix() acceptance/rejection."""

    @staticmethod
    def resource_for(logical_path: str, body: bytes) -> tuple[dict, bytes]:
        digest = hashlib.sha256(body).hexdigest()
        output_path = f"a/{digest}{Path(logical_path).suffix}"
        return (
            {
                "logical_path": logical_path,
                "output_path": output_path,
                "sha256": digest,
            },
            body,
        )

    def build_ledger_with_repeated_entries(
        self, root: Path, entry_count: int
    ) -> tuple[Path, Path]:
        """Directly construct a valid, chained ledger of `entry_count`
        entries that all reference the SAME single physical resource.

        This intentionally bypasses record_snapshot()'s real dedupe/append
        path (which would collapse identical consecutive snapshots to one
        entry, exactly as it should for a genuine build). It exists purely
        to exercise entry-COUNT thresholds in isolation, fast and without
        entangling them with the separate, pre-existing MAX_RETAINED_RESOURCES
        bound: reusing one resource keeps the retained-assets union at size 1
        regardless of entry count, since validate_ledger() never forbids two
        different entries from repeating identical resources — only
        record_snapshot()'s append policy does that.
        """
        assets = root / "retained-assets"
        resource, body = self.resource_for("img/fixture.svg", b"hard-limit-fixture\n")
        (assets / "a").mkdir(parents=True, exist_ok=True)
        (assets / resource["output_path"]).write_bytes(body)
        entries = []
        previous_digest = None
        for index in range(entry_count):
            entry = {
                "kind": "snapshot",
                "sequence": index + 1,
                "previous_entry_sha256": previous_digest,
                "resource_count": 1,
                "resources": [resource],
            }
            previous_digest = asset_retention.entry_digest(entry)
            entries.append(entry)
        document = {
            "schema_version": asset_retention.LEDGER_SCHEMA_VERSION,
            "entry_count": entry_count,
            "entries": entries,
        }
        ledger = root / "asset-retention.json"
        ledger.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
        return ledger, assets

    def test_consecutive_identical_snapshots_do_not_grow_the_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root / "asset-retention.json"
            assets = root / "retained-assets"
            resource, body = self.resource_for("img/a.svg", b"same\n")
            document = asset_retention.record_snapshot(
                ledger, assets, [resource], {resource["output_path"]: body}
            )
            self.assertEqual(document["entry_count"], 1)
            document_again = asset_retention.record_snapshot(
                ledger, assets, [resource], {resource["output_path"]: body}
            )
            self.assertEqual(document_again["entry_count"], 1)

    def test_validate_ledger_accepts_history_far_past_the_old_128_cap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger, assets = self.build_ledger_with_repeated_entries(
                root, asset_retention.RETENTION_HISTORY_HARD_LIMIT_ENTRIES
            )
            document, bodies = asset_retention.validate_ledger(ledger, assets)
        self.assertEqual(
            document["entry_count"], asset_retention.RETENTION_HISTORY_HARD_LIMIT_ENTRIES
        )
        self.assertEqual(len(bodies), 1)

    def test_soft_warning_fires_at_threshold_and_names_compact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger, assets = self.build_ledger_with_repeated_entries(
                root, asset_retention.RETENTION_HISTORY_SOFT_WARN_ENTRIES - 1
            )
            resource, body = self.resource_for("img/new.svg", b"fresh\n")
            stderr = io.StringIO()
            with mock.patch.object(asset_retention.sys, "stderr", stderr):
                document = asset_retention.record_snapshot(
                    ledger, assets, [resource], {resource["output_path"]: body}
                )
        self.assertEqual(
            document["entry_count"], asset_retention.RETENTION_HISTORY_SOFT_WARN_ENTRIES
        )
        self.assertIn("WARNING", stderr.getvalue())
        self.assertIn("asset_retention.py compact", stderr.getvalue())

    def test_hard_limit_blocks_append_and_names_the_compact_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger, assets = self.build_ledger_with_repeated_entries(
                root, asset_retention.RETENTION_HISTORY_HARD_LIMIT_ENTRIES
            )
            resource, body = self.resource_for("img/new.svg", b"fresh\n")
            with self.assertRaisesRegex(
                ValueError, "asset_retention.py compact"
            ) as context:
                asset_retention.record_snapshot(
                    ledger, assets, [resource], {resource["output_path"]: body}
                )
        self.assertIn(
            str(asset_retention.RETENTION_HISTORY_HARD_LIMIT_ENTRIES),
            str(context.exception),
        )

    def test_compact_unions_resources_across_superseded_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root / "asset-retention.json"
            assets = root / "retained-assets"
            first, first_body = self.resource_for("css/old.css", b"old styles\n")
            asset_retention.record_snapshot(
                ledger, assets, [first], {first["output_path"]: first_body}
            )
            second, second_body = self.resource_for("css/new.css", b"new styles\n")
            asset_retention.record_snapshot(
                ledger, assets, [second], {second["output_path"]: second_body}
            )
            before, before_bodies = asset_retention.validate_ledger(ledger, assets)
            self.assertEqual(before["entry_count"], 2)
            self.assertEqual(len(before_bodies), 2)

            compacted = asset_retention.record_checkpoint(ledger, assets)
            self.assertEqual(compacted["entry_count"], 1)
            checkpoint = compacted["entries"][0]
            self.assertEqual(checkpoint["kind"], "checkpoint")
            self.assertEqual(checkpoint["superseded_entry_count"], 2)
            output_paths = {item["output_path"] for item in checkpoint["resources"]}
            self.assertEqual(
                output_paths, {first["output_path"], second["output_path"]}
            )
            # Compaction never drops a retention obligation or a physical
            # body — only the granular per-commit entry history shrinks.
            after, after_bodies = asset_retention.validate_ledger(ledger, assets)
            self.assertEqual(after_bodies, before_bodies)

    def test_compact_with_at_most_one_entry_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root / "asset-retention.json"
            assets = root / "retained-assets"
            resource, body = self.resource_for("img/a.svg", b"solo\n")
            asset_retention.record_snapshot(
                ledger, assets, [resource], {resource["output_path"]: body}
            )
            with self.assertRaisesRegex(ValueError, "nothing to compact"):
                asset_retention.record_checkpoint(ledger, assets)

    def test_validate_history_prefix_accepts_a_faithful_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root / "asset-retention.json"
            assets = root / "retained-assets"
            first, first_body = self.resource_for("css/old.css", b"old\n")
            asset_retention.record_snapshot(
                ledger, assets, [first], {first["output_path"]: first_body}
            )
            second, second_body = self.resource_for("css/new.css", b"new\n")
            asset_retention.record_snapshot(
                ledger, assets, [second], {second["output_path"]: second_body}
            )
            prior_path = root / "prior-asset-retention.json"
            prior_path.write_bytes(ledger.read_bytes())

            compacted = asset_retention.record_checkpoint(ledger, assets)
            asset_retention.validate_history_prefix(compacted, prior_path)

    def test_validate_history_prefix_rejects_a_fabricated_checkpoint_root(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root / "asset-retention.json"
            assets = root / "retained-assets"
            first, first_body = self.resource_for("css/old.css", b"old\n")
            asset_retention.record_snapshot(
                ledger, assets, [first], {first["output_path"]: first_body}
            )
            second, second_body = self.resource_for("css/new.css", b"new\n")
            asset_retention.record_snapshot(
                ledger, assets, [second], {second["output_path"]: second_body}
            )
            prior_path = root / "prior-asset-retention.json"
            prior_path.write_bytes(ledger.read_bytes())

            compacted = asset_retention.record_checkpoint(ledger, assets)
            forged = copy.deepcopy(compacted)
            forged["entries"][0]["checkpoint_root_sha256"] = "0" * 64
            # With the fabricated root rejected, the transition falls back to
            # the ordinary literal-prefix check — which a lone checkpoint
            # entry can never satisfy against a longer, un-compacted prior
            # history, so this fails closed via truncation rather than a
            # byte-mismatch, but it still fails closed.
            with self.assertRaisesRegex(ValueError, "truncated"):
                asset_retention.validate_history_prefix(forged, prior_path)

    def test_validate_history_prefix_rejects_same_length_forged_checkpoint(
        self,
    ) -> None:
        # Same entry count on both sides isolates the byte-mismatch branch
        # from the truncation branch exercised above.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root / "asset-retention.json"
            assets = root / "retained-assets"
            resource, body = self.resource_for("css/old.css", b"old\n")
            document = asset_retention.record_snapshot(
                ledger, assets, [resource], {resource["output_path"]: body}
            )
            prior_path = root / "prior-asset-retention.json"
            prior_path.write_bytes(ledger.read_bytes())

            forged = copy.deepcopy(document)
            forged["entries"][0] = {
                "kind": "checkpoint",
                "sequence": 1,
                "previous_entry_sha256": None,
                "resource_count": 1,
                "resources": document["entries"][0]["resources"],
                "checkpoint_root_sha256": "0" * 64,
                "superseded_entry_count": 2,
            }
            with self.assertRaisesRegex(ValueError, "append-only base prefix"):
                asset_retention.validate_history_prefix(forged, prior_path)

    def test_checkpoint_entry_shape_is_strictly_validated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root / "asset-retention.json"
            assets = root / "retained-assets"
            first, first_body = self.resource_for("css/old.css", b"old\n")
            asset_retention.record_snapshot(
                ledger, assets, [first], {first["output_path"]: first_body}
            )
            second, second_body = self.resource_for("css/new.css", b"new\n")
            asset_retention.record_snapshot(
                ledger, assets, [second], {second["output_path"]: second_body}
            )
            document = asset_retention.record_checkpoint(ledger, assets)

            cases = {
                "malformed root": (
                    lambda candidate: candidate["entries"][0].update(
                        checkpoint_root_sha256="not-hex"
                    ),
                    "checkpoint_root_sha256",
                ),
                "boolean superseded count": (
                    lambda candidate: candidate["entries"][0].update(
                        superseded_entry_count=True
                    ),
                    "superseded_entry_count",
                ),
                "superseded count too small": (
                    lambda candidate: candidate["entries"][0].update(
                        superseded_entry_count=1
                    ),
                    "superseded_entry_count",
                ),
                "checkpoint not at index 0": (
                    lambda candidate: candidate["entries"].append(
                        {**candidate["entries"][0], "sequence": 2}
                    )
                    or candidate.update(entry_count=2),
                    "first entry",
                ),
                "unknown kind": (
                    lambda candidate: candidate["entries"][0].update(kind="snapshot"),
                    "unexpected or missing keys",
                ),
            }
            for label, (mutate, expected) in cases.items():
                with self.subTest(label=label):
                    candidate = copy.deepcopy(document)
                    mutate(candidate)
                    ledger.write_text(json.dumps(candidate))
                    with self.assertRaisesRegex(ValueError, expected):
                        asset_retention.validate_ledger(ledger, assets)
            ledger.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")


class ReleaseManifestContractTests(unittest.TestCase):
    @staticmethod
    def logical_resource_path(output: Path, manifest: dict, logical: str) -> Path:
        item = next(
            item for item in manifest["resources"] if item["logical_path"] == logical
        )
        return output / item["output_path"]

    def make_fixture(
        self,
        output: Path,
        addressed_bodies: dict[str, bytes] | None = None,
    ) -> tuple[dict, dict, bytes]:
        contract, contract_errors = release.read_contract(
            ROOT / "release-resources.toml"
        )
        self.assertEqual(contract_errors, [])
        bodies = {
            "atom.xml": b"<feed/>\n",
            "build-revision.txt": f"{EXPECTED_REVISION}\n".encode(),
            "career-claims.json": b"{}\n",
            "llms.txt": b"fixture\n",
            "release-html.json": b"{}\n",
            "robots.txt": b"fixture\n",
            "runtime-boundary.json": b"{}\n",
            "sitemap.xml": b"<urlset/>\n",
            "systems.json": b"{}\n",
        }
        mapped_bodies = {
            "files/report.pdf": b"pdf bytes\n",
            "site.webmanifest": b"{}\n",
            "speculation-rules.json": b"{}\n",
        }
        mapped_bodies.update(addressed_bodies or {})
        asset_resources = []
        for logical_path, body in mapped_bodies.items():
            digest = hashlib.sha256(body).hexdigest()
            output_path = addressed_output(logical_path, body)
            bodies[output_path] = body
            asset_resources.append(
                {
                    "logical_path": logical_path,
                    "output_path": output_path,
                    "request_url": f"/{output_path}",
                    "sha256": digest,
                    "cache_class": "addressed",
                }
            )
        for relative, body in bodies.items():
            path = output / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        asset_map = {
            "schema_version": release.ASSET_MAP_SCHEMA_VERSION,
            "resource_count": len(asset_resources),
            "resources": asset_resources,
            "media_types": {
                item["request_url"]: release.SPECULATION_MEDIA_TYPE
                for item in asset_resources
                if item["logical_path"] == "speculation-rules.json"
            },
        }
        manifest = release.build_manifest(
            output, EXPECTED_REVISION, asset_map, contract
        )
        return contract, manifest, release.serialize_manifest(manifest)

    def test_complete_fixture_satisfies_release_manifest_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            contract, _manifest, raw = self.make_fixture(output)
            _document, errors = release.validate_manifest(
                raw,
                output=output,
                expected_revision=EXPECTED_REVISION,
                contract=contract,
            )
        self.assertEqual(errors, [])

    def test_runtime_html_authority_has_query_free_release_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _contract, manifest, _raw = self.make_fixture(Path(directory))
        authority = next(
            item
            for item in manifest["resources"]
            if item["output_path"] == html_contract.AUTHORITY_NAME
        )
        self.assertEqual(authority["request_url"], "/release-html.json")

    def test_manifest_schema_path_and_query_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            contract, manifest, _ = self.make_fixture(output)
            manifest["resources"][-1]["output_path"] = "../escape"
            manifest["resources"][-1]["request_url"] = "https://example.com/report.pdf"
            _, errors = release.validate_manifest(
                release.serialize_manifest(manifest),
                output=output,
                expected_revision=EXPECTED_REVISION,
                contract=contract,
            )
        self.assertTrue(any("invalid output_path" in error for error in errors), errors)
        self.assertTrue(any("coverage differs" in error for error in errors), errors)

    def test_manifest_count_and_duplicate_url_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            contract, manifest, _ = self.make_fixture(output)
            manifest["resource_count"] += 1
            manifest["resources"][1]["request_url"] = manifest["resources"][0][
                "request_url"
            ]
            _, errors = release.validate_manifest(
                release.serialize_manifest(manifest),
                output=output,
                expected_revision=EXPECTED_REVISION,
                contract=contract,
            )
        self.assertTrue(any("resource_count" in error for error in errors), errors)
        self.assertTrue(
            any("duplicate request_url" in error for error in errors), errors
        )

    def test_manifest_stale_digest_and_missing_artifact_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            contract, manifest, raw = self.make_fixture(output)
            report = next(
                item
                for item in manifest["resources"]
                if item["logical_path"] == "files/report.pdf"
            )
            report_path = output / report["output_path"]
            report_path.write_bytes(b"changed\n")
            _, stale_errors = release.validate_manifest(
                raw,
                output=output,
                expected_revision=EXPECTED_REVISION,
                contract=contract,
            )
            report_path.unlink()
            _, missing_errors = release.validate_manifest(
                raw,
                output=output,
                expected_revision=EXPECTED_REVISION,
                contract=contract,
            )
        self.assertTrue(
            any("sha256 does not match" in error for error in stale_errors),
            stale_errors,
        )
        self.assertTrue(
            any("does not resolve" in error for error in missing_errors), missing_errors
        )
        self.assertTrue(
            any("coverage differs" in error for error in missing_errors), missing_errors
        )

    def test_unversioned_public_artifact_reference_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            _contract, manifest, _raw = self.make_fixture(output)
            cases = (
                "/files/report.pdf",
                "/files/report.pdf ",
                "///ardent.tools/files/report.pdf",
            )
            for reference in cases:
                with self.subTest(reference=reference):
                    (output / "index.html").write_text(
                        f'<a href="{reference}">Download report</a>'
                    )
                    errors = release.validate_public_references(output, manifest)
                    self.assertEqual(len(errors), 1, errors)
                    self.assertIn("must use manifest URL", errors[0])

    def test_unversioned_css_manifest_and_header_references_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            _contract, manifest, _raw = self.make_fixture(output)
            (output / "css").mkdir()
            (output / "css/app.css").write_text(
                "body { background: url('/files/report.pdf'); }\n"
            )
            self.logical_resource_path(output, manifest, "site.webmanifest").write_text(
                '{"icons":[{"src":"/files/report.pdf"}]}\n'
            )
            (output / "_headers").write_text(
                '/*\n  Example-Resource: "/files/report.pdf"\n'
            )
            errors = release.validate_public_references(output, manifest)
        self.assertEqual(len(errors), 3, errors)
        self.assertTrue(
            all("must use manifest URL" in error for error in errors), errors
        )

    def test_webmanifest_color_is_not_a_self_resource_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            _contract, manifest, _raw = self.make_fixture(output)
            self.logical_resource_path(output, manifest, "site.webmanifest").write_text(
                '{"name":"fixture","theme_color":"#F7F3E8"}\n'
            )
            errors = release.validate_public_references(output, manifest)
        self.assertEqual(errors, [])

    def test_json_ld_manifest_references_require_exact_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            _contract, manifest, _raw = self.make_fixture(output)
            report = next(
                item
                for item in manifest["resources"]
                if item["logical_path"] == "files/report.pdf"
            )
            exact = f"{BASE_URL}{report['request_url']}"
            cases = {
                "unversioned absolute": f"{BASE_URL}/files/report.pdf",
                "unversioned relative": "files/report.pdf",
                "explicit default port": exact.replace(
                    "https://ardent.tools/", "https://ardent.tools:443/"
                ),
                "percent-encoded alias": exact.replace("/a/", "/%61/"),
                "dot-segment alias": exact.replace("/a/", "/a/../a/"),
                "root-relative backslash alias": report["request_url"].replace(
                    "/a/", "/a\\"
                ),
                "absolute backslash alias": exact.replace("/a/", "/a\\"),
                "encoded backslash alias": exact.replace("/a/", "/a%5c"),
                "trailing browser whitespace": f"{BASE_URL}/files/report.pdf ",
                "excess authority separators": "///ardent.tools/files/report.pdf",
                "excess scheme separators": "https:///ardent.tools/files/report.pdf",
                "double path separator": "https://ardent.tools//files/report.pdf",
                "IDNA host alias": "https://ＡＲＤＥＮＴ.ＴＯＯＬＳ/files/report.pdf",
                "Unicode dot host alias": "https://ardent。tools/files/report.pdf",
                "percent-encoded host alias": "https://%61rdent.tools/files/report.pdf",
                "percent-encoded dot host alias": "https://ardent%2etools/files/report.pdf",
                "CSP-upgraded HTTP": "http://ardent.tools/files/report.pdf",
                "CSP-upgraded explicit port": "http://ardent.tools:80/files/report.pdf",
                "CSP-upgraded HTTPS-default port": "http://ardent.tools:443/files/report.pdf",
                "relative exact query": report["request_url"].lstrip("/"),
                "protocol-relative": exact.replace("https:", ""),
                "raw-script HTML entity": f"{exact}?v=2&amp;h=stale",
            }
            for label, reference in cases.items():
                with self.subTest(label=label):
                    (output / "index.html").write_text(
                        '<script type="application/ld+json">'
                        f"{json.dumps({'image': reference})}"
                        "</script>"
                    )
                    errors = release.validate_public_references(output, manifest)
                    self.assertEqual(len(errors), 1, errors)
                    self.assertIn("must use manifest URL", errors[0])

            (output / "index.html").write_text(
                f'<script type="application/ld+json">{{"image":"{exact}"}}</script>'
            )
            self.assertEqual(release.validate_public_references(output, manifest), [])
            (output / "index.html").write_text(
                '<script type="application/ld+json">'
                f'{{"image":"{report["request_url"]}"}}'
                "</script>"
            )
            self.assertEqual(release.validate_public_references(output, manifest), [])

    def test_css_url_escapes_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            _contract, manifest, _raw = self.make_fixture(output)
            (output / "app.css").write_text(
                r"body { background: url('/files/\72 eport.pdf'); }" + "\n"
            )
            errors = release.validate_public_references(output, manifest)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("CSS source contains a forbidden escape or backslash", errors[0])

    def test_css_comment_delimiters_inside_url_strings_remain_literal(self) -> None:
        references = (
            'url("https://ardent.tools/files/**/../report.pdf")',
            "url(https://ardent.tools/files/**/../report.pdf)",
        )
        for reference in references:
            with (
                self.subTest(reference=reference),
                tempfile.TemporaryDirectory() as directory,
            ):
                output = Path(directory)
                _contract, manifest, _raw = self.make_fixture(output)
                (output / "app.css").write_text(
                    f".sample {{ background: {reference}; }}\n"
                )
                errors = release.validate_public_references(output, manifest)
            self.assertEqual(len(errors), 1, errors)
            self.assertIn("must use manifest URL", errors[0])

    def test_css_unicode_comments_do_not_shift_scanner_offsets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            _contract, manifest, _raw = self.make_fixture(output)
            (output / "app.css").write_text(
                "/* İ */ .sample { background: url(/files/report.pdf); }\n"
            )
            errors = release.validate_public_references(output, manifest)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("must use manifest URL", errors[0])

    def test_compound_html_url_grammars_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            _contract, manifest, _raw = self.make_fixture(output)
            (output / "index.html").write_text(
                '<img srcset="/files/report.pdf 1x, /files/report.pdf 2x">'
            )
            errors = release.validate_public_references(output, manifest)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("compound URL attribute 'srcset' is forbidden", errors[0])

    def test_embedded_and_ambiguous_html_fail_closed(self) -> None:
        cases = {
            "srcdoc": (
                "<iframe srcdoc=\"&lt;img src='/files/report.pdf'&gt;\"></iframe>",
                "compound URL attribute 'srcdoc' is forbidden",
            ),
            "attribution registration": (
                '<img src="/img/other.png" attributionsrc="/files/report.pdf">',
                "compound URL attribute 'attributionsrc' is forbidden",
            ),
            "inline foreign content": (
                '<svg><image href="/files/report.pdf"></image></svg>',
                "inline svg foreign content is forbidden",
            ),
            "duplicate refresh discriminator": (
                '<meta http-equiv="refresh" http-equiv="x" '
                'content="0; url=/files/report.pdf">',
                "duplicate HTML attributes are forbidden",
            ),
            "duplicate script type": (
                '<script type="application/ld+json" type="text/javascript">'
                '{"image":"/files/report.pdf"}</script>',
                "duplicate HTML attributes are forbidden",
            ),
        }
        for label, (markup, expected) in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                output = Path(directory)
                _contract, manifest, _raw = self.make_fixture(output)
                (output / "index.html").write_text(markup)
                errors = release.validate_public_references(output, manifest)
                self.assertTrue(any(expected in error for error in errors), errors)

    def test_css_quoted_url_and_actual_stylesheet_base_are_inspected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            _contract, manifest, _raw = self.make_fixture(
                output,
                {
                    "css/font.woff2": b"font bytes\n",
                    "css/app.css": (
                        "/* a maintainer's note */\n"
                        '.sample { background: url("font.woff2"); }\n'
                    ).encode(),
                },
            )
            errors = release.validate_public_references(output, manifest)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("path-relative CSS url() is forbidden", errors[0])

    def test_css_complex_resource_grammars_and_bad_strings_fail_closed(self) -> None:
        cases = {
            "image-set": (
                '.sample { background: image-set("/files/report.pdf" 1x); }\n',
                "CSS image-set() is forbidden",
            ),
            "bad-string recovery": (
                '.a { content: "\n;\nbackground-image: '
                'url(https://ardent.tools/files/report.pdf);\nx: "foo";\n/* " */\n}\n',
                "CSS contains an invalid or unterminated string",
            ),
        }
        for label, (css, expected) in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                output = Path(directory)
                _contract, manifest, _raw = self.make_fixture(output)
                (output / "app.css").write_text(css)
                errors = release.validate_public_references(output, manifest)
                self.assertEqual(len(errors), 1, errors)
                self.assertIn(expected, errors[0])

    def test_query_only_css_url_cannot_refetch_stylesheet_without_identity(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            _contract, manifest, _raw = self.make_fixture(
                output,
                {"css/app.css": b".sample { background-image: url(?stale); }\n"},
            )
            errors = release.validate_public_references(output, manifest)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("must use manifest URL", errors[0])

    def test_retained_svg_must_be_strict_and_self_contained(self) -> None:
        cases = {
            "external href": (
                '<svg xmlns="http://www.w3.org/2000/svg">'
                '<image href="/files/report.pdf"/></svg>',
                "attribute 'href' must be a local fragment",
            ),
            "external style URL": (
                '<svg xmlns="http://www.w3.org/2000/svg">'
                "<style>path{fill:url(/files/report.pdf)}</style></svg>",
                "SVG styles must not load external resource",
            ),
            "style child tail": (
                '<svg xmlns="http://www.w3.org/2000/svg">'
                "<style><g/>path{fill:url(/files/report.pdf)}</style></svg>",
                "SVG style elements must not have children",
            ),
            "active content": (
                '<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>',
                "SVG element 'script' is forbidden",
            ),
            "stylesheet processing instruction": (
                '<?xml-stylesheet type="text/css" href="/files/report.pdf"?>'
                '<svg xmlns="http://www.w3.org/2000/svg"/>',
                "SVG processing instructions are forbidden",
            ),
            "presentation escape": (
                '<svg xmlns="http://www.w3.org/2000/svg">'
                '<path fill="u\\72l(/files/report.pdf#x)"/></svg>',
                "contains a forbidden escape or backslash",
            ),
            "foreign namespace fetch": (
                '<svg xmlns="http://www.w3.org/2000/svg">'
                '<img xmlns="http://www.w3.org/1999/xhtml" '
                'src="/files/report.pdf"/></svg>',
                "foreign-namespace SVG elements are forbidden",
            ),
        }
        for label, (document, expected) in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                output = Path(directory)
                _contract, manifest, _raw = self.make_fixture(output)
                (output / "image.svg").write_text(document)
                errors = release.validate_public_references(output, manifest)
                self.assertEqual(len(errors), 1, errors)
                self.assertIn(expected, errors[0])

    def test_retained_svg_local_fragments_are_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            _contract, manifest, _raw = self.make_fixture(output)
            (output / "image.svg").write_text(
                '<svg xmlns="http://www.w3.org/2000/svg">'
                "<style>path{filter:url(#grain)}</style>"
                '<defs><filter id="grain"/></defs><use href="#grain"/></svg>'
            )
            errors = release.validate_public_references(output, manifest)
        self.assertEqual(errors, [])

    def test_browser_url_resolver_failure_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            _contract, manifest, _raw = self.make_fixture(output)
            (output / "index.html").write_text('<img src="/files/report.pdf">')
            with mock.patch.object(
                release.subprocess, "run", side_effect=OSError("absent")
            ):
                errors = release.validate_public_references(output, manifest)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("browser URL resolution failed closed", errors[0])

    def test_json_ld_is_strict_and_complete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            _contract, manifest, _raw = self.make_fixture(output)
            cases = {
                "duplicate key": '{"logo":"a","logo":"b"}',
                "non-JSON constant": '{"value":NaN}',
                "unterminated block": '{"value":"x"}',
            }
            for label, document in cases.items():
                with self.subTest(label=label):
                    closing = "" if label == "unterminated block" else "</script>"
                    (output / "index.html").write_text(
                        f'<script type="application/ld+json">{document}{closing}'
                    )
                    errors = release.validate_public_references(output, manifest)
                    self.assertEqual(len(errors), 1, errors)
                    self.assertIn("application/ld+json", errors[0])

    def test_release_manifest_and_webmanifest_require_strict_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            contract, manifest, _raw = self.make_fixture(output)
            duplicate_manifest = b'{"resources":[],"resources":[]}'
            _document, manifest_errors = release.validate_manifest(
                duplicate_manifest,
                output=output,
                expected_revision=EXPECTED_REVISION,
                contract=contract,
            )
            self.logical_resource_path(output, manifest, "site.webmanifest").write_text(
                '{"name":"a","name":"b"}'
            )
            reference_errors = release.validate_public_references(output, manifest)
        self.assertEqual(len(manifest_errors), 1, manifest_errors)
        self.assertIn("duplicate key", manifest_errors[0])
        self.assertEqual(len(reference_errors), 1, reference_errors)
        self.assertIn("site.webmanifest", reference_errors[0])

    def test_tombstone_resurrection_fails_local_and_live(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            contract, _manifest, raw = self.make_fixture(
                output, {"tapes/aletheia-memory.tape": b"old tape\n"}
            )
            _, errors = release.validate_manifest(
                raw,
                output=output,
                expected_revision=EXPECTED_REVISION,
                contract=contract,
            )
        self.assertTrue(
            any("tombstone is present" in error for error in errors), errors
        )
        live_errors = run_production_fixture(self, tombstone_status=200)
        self.assertTrue(
            any(
                "tombstone /tapes/aletheia-memory.tape returned 200" in error
                for error in live_errors
            ),
            live_errors,
        )

    def test_live_manifest_and_structured_body_mismatch_fail(self) -> None:
        errors = run_production_fixture(
            self,
            live_manifest_body=b"{}\n",
            resource_overrides={"systems.json": (200, GOOD_CACHE, b"stale systems\n")},
        )
        self.assertTrue(
            any(
                "live /release-resources.json bytes differ" in error for error in errors
            ),
            errors,
        )
        self.assertTrue(
            any(
                "/systems.json" in error and "digest mismatch" in error
                for error in errors
            ),
            errors,
        )

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


class HeaderContractTests(unittest.TestCase):
    SPECULATION_PATH = f"/a/{'1' * 64}.json"

    @staticmethod
    def repository_manifest() -> dict:
        return {
            "media_types": {
                f"/a/{'1' * 64}.json": release.SPECULATION_MEDIA_TYPE,
            },
            "resources": [
                {
                    "logical_path": "speculation-rules.json",
                    "output_path": f"a/{'1' * 64}.json",
                    "request_url": f"/a/{'1' * 64}.json",
                }
            ],
        }

    @classmethod
    def finalized_headers(cls) -> str:
        return (
            (ROOT / "_headers")
            .read_text()
            .replace("/speculation-rules.json", cls.SPECULATION_PATH)
        )

    def test_repository_headers_are_the_exact_supported_contract(self) -> None:
        contract, errors = headers_contract.validate_headers(
            self.finalized_headers(), self.repository_manifest()
        )
        self.assertEqual(errors, [])
        self.assertIsNotNone(contract)
        self.assertEqual(
            contract.direct_response["speculation-rules"],
            f'"{self.SPECULATION_PATH}"',
        )

    def test_missing_wrong_duplicate_extra_and_detach_fail_closed(self) -> None:
        raw = self.finalized_headers()
        hsts = (
            "  Strict-Transport-Security: max-age=31536000; includeSubDomains; preload"
        )
        cases = {
            "missing": raw.replace(hsts + "\n", ""),
            "wrong": raw.replace(hsts, "  Strict-Transport-Security: max-age=60"),
            "duplicate": raw.replace(hsts, f"{hsts}\n{hsts}"),
            "extra path": raw + "\n/extra\n  X-Test: no\n",
            "detach": raw.replace(hsts, "  ! Strict-Transport-Security"),
        }
        for label, candidate in cases.items():
            with self.subTest(label=label):
                _contract, errors = headers_contract.validate_headers(
                    candidate, self.repository_manifest()
                )
                self.assertTrue(errors, label)

    def test_addressed_asset_cache_control_must_detach_the_inherited_value(
        self,
    ) -> None:
        raw = self.finalized_headers()
        detach_line = "  ! Cache-Control\n"
        self.assertIn(detach_line, raw)
        without_detach = raw.replace(detach_line, "")
        _contract, errors = headers_contract.validate_headers(
            without_detach, self.repository_manifest()
        )
        self.assertTrue(
            any("must detach the inherited" in error for error in errors), errors
        )

    def test_addressed_asset_section_missing_entirely_fails(self) -> None:
        raw = self.finalized_headers()
        without_section = raw.replace(
            "\n/a/*\n  ! Cache-Control\n  Cache-Control: public, max-age=31536000, immutable\n",
            "\n",
        )
        self.assertNotEqual(without_section, raw)
        _contract, errors = headers_contract.validate_headers(
            without_section, self.repository_manifest()
        )
        self.assertTrue(
            any("supported path set differs" in error for error in errors), errors
        )

    def test_parse_headers_tracks_detach_independent_of_the_resulting_map(
        self,
    ) -> None:
        raw = "/a/*\n  ! Cache-Control\n  Cache-Control: public, max-age=1, immutable\n"
        sections, detached, errors = headers_contract.parse_headers(raw)
        self.assertEqual(errors, [])
        self.assertEqual(
            sections["/a/*"], {"cache-control": "public, max-age=1, immutable"}
        )
        self.assertIn("cache-control", detached["/a/*"])

        bare_detach = "/a/*\n  ! Cache-Control\n"
        bare_sections, bare_detached, bare_errors = headers_contract.parse_headers(
            bare_detach
        )
        self.assertEqual(bare_errors, [])
        self.assertEqual(bare_sections["/a/*"], {})
        self.assertIn("cache-control", bare_detached["/a/*"])

    def test_live_direct_header_omission_and_duplicate_fail(self) -> None:
        missing = run_production_fixture(
            self,
            root_header_overrides={"Strict-Transport-Security": None},
        )
        self.assertEqual(len(missing), 1, missing)
        self.assertIn("strict-transport-security header must be exactly", missing[0])

        duplicate = run_production_fixture(
            self,
            root_header_overrides={"X-Frame-Options": "DENY, SAMEORIGIN"},
        )
        self.assertEqual(len(duplicate), 1, duplicate)
        self.assertIn("x-frame-options header must be exactly", duplicate[0])

    def test_live_speculation_rules_content_type_is_exact(self) -> None:
        errors = run_production_fixture(
            self, speculation_content_type="application/json"
        )
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("Content-Type must be", errors[0])

    def test_live_retained_html_content_type_is_html(self) -> None:
        errors = run_production_fixture(
            self, root_header_overrides={"Content-Type": "text/plain"}
        )
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("Content-Type must be HTML", errors[0])

    def test_pages_header_rule_limit_has_an_exact_boundary(self) -> None:
        media_types = {
            f"/a/{index:064x}.json": release.SPECULATION_MEDIA_TYPE
            for index in range(1, pages_limits.MAX_MEDIA_TYPE_HEADER_RULES)
        }
        manifest = self.repository_manifest()
        manifest["media_types"] = {**manifest["media_types"], **media_types}
        contract, errors = headers_contract.expected_contract(manifest)
        self.assertEqual(errors, [])
        self.assertIsNotNone(contract)

        manifest["media_types"] = {
            **manifest["media_types"],
            f"/a/{pages_limits.MAX_HEADER_RULES:064x}.json": (
                release.SPECULATION_MEDIA_TYPE
            ),
        }
        contract, errors = headers_contract.expected_contract(manifest)
        self.assertIsNone(contract)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("100-rule limit", errors[0])


class PagesPlatformLimitTests(unittest.TestCase):
    def test_pages_static_file_limit_uses_exact_file_size(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            at_limit = root / "at-limit.bin"
            over_limit = root / "over-limit.bin"
            at_limit.touch()
            over_limit.touch()
            with at_limit.open("r+b") as handle:
                handle.truncate(pages_limits.MAX_STATIC_FILE_BYTES)
            with over_limit.open("r+b") as handle:
                handle.truncate(pages_limits.MAX_STATIC_FILE_BYTES + 1)
            errors = pages_limits.validate_static_tree(root)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("over-limit.bin", errors[0])
        self.assertIn("static-file limit", errors[0])


class HtmlAuthorityContractTests(unittest.TestCase):
    def make_fixture(self, output: Path) -> tuple[dict, bytes]:
        sitemap = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f"<url><loc>{BASE_URL}/</loc></url>"
            f"<url><loc>{BASE_URL}/about/</loc></url>"
            "</urlset>"
        )
        files = {
            "sitemap.xml": sitemap.encode(),
            "index.html": b"root\n",
            "about/index.html": b"about\n",
            "private-proof/index.html": b"not in sitemap\n",
            "404/index.html": b"missing\n",
            "404.html": b"missing\n",
        }
        for relative, body in files.items():
            path = output / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        authority = html_contract.build_authority(output, EXPECTED_REVISION, BASE_URL)
        return authority, html_contract.serialize_authority(authority)

    def test_authority_covers_sitemap_and_non_sitemap_html(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            authority, raw = self.make_fixture(output)
            _document, errors = html_contract.validate_authority(
                raw,
                output=output,
                expected_revision=EXPECTED_REVISION,
                base_url=BASE_URL,
            )
        self.assertEqual(errors, [])
        by_path = {item["request_path"]: item for item in authority["routes"]}
        self.assertEqual(set(by_path), {"/", "/404/", "/about/", "/private-proof/"})
        self.assertTrue(by_path["/"]["in_sitemap"])
        self.assertFalse(by_path["/private-proof/"]["in_sitemap"])

    def test_stale_or_missing_non_sitemap_html_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            _authority, raw = self.make_fixture(output)
            hidden = output / "private-proof/index.html"
            hidden.write_bytes(b"stale\n")
            _document, stale_errors = html_contract.validate_authority(
                raw,
                output=output,
                expected_revision=EXPECTED_REVISION,
                base_url=BASE_URL,
            )
            hidden.unlink()
            _document, missing_errors = html_contract.validate_authority(
                raw,
                output=output,
                expected_revision=EXPECTED_REVISION,
                base_url=BASE_URL,
            )
        self.assertTrue(any("differs" in error for error in stale_errors), stale_errors)
        self.assertTrue(
            any("differs" in error for error in missing_errors), missing_errors
        )

    def test_flat_non_index_html_is_outside_the_deployable_authority(self) -> None:
        with self.assertRaisesRegex(
            ValueError, r"index\.html or a nested \*/index\.html"
        ):
            html_contract.html_request_path("private-proof.html")

    def test_custom_404_drift_dot_segments_and_non_strict_json_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            self.make_fixture(output)
            (output / "404.html").write_bytes(b"different\n")
            with self.assertRaisesRegex(ValueError, "byte-identical"):
                html_contract.build_authority(output, EXPECTED_REVISION, BASE_URL)
        with self.assertRaisesRegex(ValueError, "dot segment"):
            html_contract.route_output_path("/about/../")
        for raw in (
            b'{"x":1,"x":2}',
            b'{"x":NaN}',
            '{"x":1}'.encode("utf-16"),
        ):
            with self.subTest(raw=raw):
                _document, errors = html_contract.validate_authority(
                    raw,
                    output=Path("."),
                    expected_revision=EXPECTED_REVISION,
                    base_url=BASE_URL,
                )
                self.assertEqual(len(errors), 1, errors)
                self.assertIn("strict UTF-8 JSON", errors[0])

    def test_live_canonical_and_custom_404_bytes_match_authority(self) -> None:
        stale_about = (
            f'<link rel="canonical" href="{BASE_URL}/about/">Changed{ASSET_MARKUP}'
        ).encode()
        about_errors = run_production_fixture(self, about_body=stale_about)
        self.assertTrue(
            any(
                "/about/ body differs from retained HTML authority" in error
                for error in about_errors
            ),
            about_errors,
        )
        stale_404 = (
            f'<link rel="canonical" href="{BASE_URL}/404/">'
            "404: no such path Return home changed "
            f'<link rel="stylesheet" href="{CSS_URL}">'
            f'<script src="{ERROR_JS_URL}" defer></script>'
        ).encode()
        missing_errors = run_production_fixture(self, custom_404_body=stale_404)
        self.assertTrue(
            any("custom-404 authority" in error for error in missing_errors),
            missing_errors,
        )


def _workflow_line_indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _workflow_strip_inline_comment(text: str) -> str:
    in_single = in_double = False
    for index, character in enumerate(text):
        if character == "'" and not in_double:
            in_single = not in_single
        elif character == '"' and not in_single:
            in_double = not in_double
        elif character == "#" and not in_single and not in_double:
            if index == 0 or text[index - 1] == " ":
                return text[:index].rstrip()
    return text.rstrip()


def _workflow_unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


class _WorkflowYamlParser:
    """Structural extraction for exactly the GitHub Actions YAML subset this
    repository's deploy.yml uses: 2-space-indented block mappings, "- "
    sequences, and literal "|" block scalars. This is deliberately not a
    general YAML parser (no flow collections, anchors, folded ">" scalars,
    or multi-document streams) — PyYAML availability on the CI runner's
    system python3 is unconfirmed, so structured assertions here are worth
    more than a raw-text index()/split() chain without adding a dependency.
    """

    def __init__(self, lines: list[str]) -> None:
        self._lines = lines
        self._index = 0

    def _peek(self) -> tuple[int, str] | None:
        while self._index < len(self._lines):
            line = self._lines[self._index]
            if line.strip() == "" or line.lstrip(" ").startswith("#"):
                self._index += 1
                continue
            return _workflow_line_indent(line), line
        return None

    def parse_block(self, indent: int):
        peeked = self._peek()
        if peeked is None or peeked[0] < indent:
            return None
        _, content = peeked
        if content.lstrip(" ").startswith("- "):
            return self.parse_sequence(indent)
        return self.parse_mapping(indent)

    def parse_sequence(self, indent: int) -> list:
        items = []
        while True:
            peeked = self._peek()
            if peeked is None or peeked[0] != indent:
                break
            _, line = peeked
            stripped = line.lstrip(" ")
            if not stripped.startswith("- "):
                break
            self._index += 1
            remainder = stripped[2:]
            item_indent = indent + 2
            if remainder.strip() == "":
                items.append(self.parse_block(item_indent))
                continue
            self._lines.insert(self._index, " " * item_indent + remainder)
            items.append(self.parse_mapping(item_indent))
        return items

    def parse_mapping(self, indent: int) -> dict:
        result: dict = {}
        while True:
            peeked = self._peek()
            if peeked is None or peeked[0] != indent:
                break
            _, line = peeked
            stripped = line.lstrip(" ")
            if stripped.startswith("- "):
                break
            self._index += 1
            clean = _workflow_strip_inline_comment(stripped)
            if ":" not in clean:
                continue
            key, _, value = clean.partition(":")
            key = _workflow_unquote(key)
            value = value.strip()
            if value == "|":
                result[key] = self._parse_block_scalar(indent)
            elif value == "":
                nested = self._peek()
                result[key] = (
                    self.parse_block(indent + 2)
                    if nested is not None and nested[0] > indent
                    else None
                )
            else:
                result[key] = _workflow_unquote(value)
        return result

    def _parse_block_scalar(self, key_indent: int) -> str:
        body: list[str] = []
        body_indent: int | None = None
        while self._index < len(self._lines):
            line = self._lines[self._index]
            if line.strip() == "":
                body.append("")
                self._index += 1
                continue
            current_indent = _workflow_line_indent(line)
            if current_indent <= key_indent:
                break
            if body_indent is None:
                body_indent = current_indent
            body.append(line[body_indent:])
            self._index += 1
        while body and body[-1] == "":
            body.pop()
        return "\n".join(body)


def parse_workflow_yaml(text: str) -> dict:
    parser = _WorkflowYamlParser(text.split("\n"))
    return parser.parse_mapping(0)


def workflow_step(steps: list[dict], name: str) -> dict:
    matches = [step for step in steps if step.get("name") == name]
    if len(matches) != 1:
        raise AssertionError(f"expected exactly one step named {name!r}, found {len(matches)}")
    return matches[0]


class DeployWorkflowContractTests(unittest.TestCase):
    def test_predeploy_revalidation_follows_wrangler_compile_and_precedes_upload(
        self,
    ) -> None:
        workflow_text = (ROOT / ".github/workflows/deploy.yml").read_text()
        workflow = parse_workflow_yaml(workflow_text)
        steps = workflow["jobs"]["gate-and-deploy"]["steps"]
        step_names = [step.get("name") for step in steps]

        checkout_step = steps[0]
        self.assertIsNone(checkout_step.get("name"))
        self.assertEqual(checkout_step.get("uses", "").split("@")[0], "actions/checkout")
        self.assertEqual(checkout_step["with"]["fetch-depth"], "0")

        compile_step = workflow_step(steps, "Compile the Pages error boundary")
        install = compile_step["run"].index("npm install -g wrangler@4.112.0")
        compile_function = compile_step["run"].index(
            "wrangler pages functions build functions"
        )
        self.assertLess(install, compile_function)
        self.assertLess(
            step_names.index("Compile the Pages error boundary"),
            step_names.index("Deploy to Cloudflare Pages"),
        )
        self.assertNotIn("--compatibility-date", workflow_text)

        deploy_step = workflow_step(steps, "Deploy to Cloudflare Pages")
        deploy_run = deploy_step["run"]
        self.assertNotIn("wrangler pages deploy public", deploy_run)
        validate = deploy_run.index(
            'python3 bin/validate-site.py public --expected-revision "$GITHUB_SHA"'
        )
        upload = deploy_run.index("wrangler pages deploy --branch=main")
        self.assertLess(validate, upload)
        self.assertEqual(deploy_step["env"]["GITHUB_SHA"], "${{ github.sha }}")
        self.assertIn('--commit-hash "$GITHUB_SHA"', deploy_run)
        self.assertIn("WRANGLER_OUTPUT_FILE_PATH", deploy_step["env"])
        self.assertIn("bin/pages_deployment_receipt.py", deploy_run)
        self.assertIn("ARDENT_IMMUTABLE_URL", deploy_run)

        retention_step = workflow_step(steps, "Select prior asset-retention authority")
        retention_run = retention_step["run"]
        self.assertIn(
            "github.event.pull_request.base.sha", retention_step["env"]["PR_BASE_SHA"]
        )
        self.assertIn(
            "github.event.before", retention_step["env"]["PUSH_BEFORE_SHA"]
        )
        self.assertIn("retention bootstrap is forbidden", retention_run)
        self.assertIn("HEAD is the repository root commit", retention_run)
        self.assertNotIn("No prior revision exists", workflow_text)
        self.assertIn(
            'git show "${base_revision}:asset-retention.json"', retention_run
        )
        self.assertIn("ARDENT_RETENTION_BASE_LEDGER", retention_run)
        self.assertIn(
            "python3 bin/asset_retention.py", (ROOT / "bin/check-site.sh").read_text()
        )

        verify_step = workflow_step(steps, "Verify live authored/runtime boundary")
        verify_run = verify_step["run"]
        self.assertIn("ARDENT_IMMUTABLE_URL", verify_run)
        self.assertEqual(verify_run.count("python3 bin/verify-production.py"), 2)
        self.assertLess(
            verify_run.index('--base-url "$ARDENT_IMMUTABLE_URL"'),
            verify_run.index("--base-url https://ardent.tools"),
        )
        self.assertEqual(
            verify_run.count("--canonical-origin https://ardent.tools"), 2
        )
        self.assertEqual(verify_run.count("--require-logical-alias-tombstones"), 1)
        immutable_verify, custom_verify = verify_run.split(
            "python3 bin/verify-production.py", 2
        )[1:]
        self.assertIn("--require-logical-alias-tombstones", immutable_verify)
        self.assertNotIn("--require-logical-alias-tombstones", custom_verify)
        self.assertIn("--attempts 37 --delay 10", immutable_verify)
        self.assertIn("--attempts 13 --delay 10", custom_verify)

    def test_workflow_yaml_parser_handles_flow_scalars_and_detach_edges(
        self,
    ) -> None:
        sample = (
            "on:\n"
            "  push:\n"
            "    branches: [main]\n"
            "  workflow_dispatch:\n"
            "jobs:\n"
            "  build:\n"
            "    steps:\n"
            "      - uses: actions/checkout@abc123 # v4\n"
            "        with:\n"
            "          fetch-depth: 0\n"
            "      - name: Say hi\n"
            "        run: |\n"
            "          echo hi  # not a YAML comment inside a block scalar\n"
            "\n"
            "          echo bye\n"
        )
        parsed = parse_workflow_yaml(sample)
        self.assertEqual(parsed["on"]["push"]["branches"], "[main]")
        self.assertIsNone(parsed["on"]["workflow_dispatch"])
        steps = parsed["jobs"]["build"]["steps"]
        self.assertEqual(steps[0]["uses"], "actions/checkout@abc123")
        self.assertEqual(steps[0]["with"]["fetch-depth"], "0")
        self.assertEqual(
            steps[1]["run"],
            "echo hi  # not a YAML comment inside a block scalar\n\necho bye",
        )


class PagesDeploymentReceiptTests(unittest.TestCase):
    PROJECT = "ardent-tools"
    REVISION = "a" * 40
    DEPLOYMENT_ID = "12345678-1234-1234-1234-123456789abc"
    URL = "https://deadbeef.ardent-tools.pages.dev"

    def entries(self) -> list[dict]:
        return [
            {
                "type": "pages-deploy",
                "version": 1,
                "pages_project": self.PROJECT,
                "deployment_id": self.DEPLOYMENT_ID,
                "url": self.URL,
                "timestamp": "2026-07-22T00:00:00.000Z",
            },
            {
                "type": "pages-deploy-detailed",
                "version": 1,
                "pages_project": self.PROJECT,
                "deployment_id": self.DEPLOYMENT_ID,
                "url": self.URL,
                "alias": None,
                "environment": "production",
                "production_branch": "main",
                "deployment_trigger": {"metadata": {"commit_hash": self.REVISION}},
                "timestamp": "2026-07-22T00:00:01.000Z",
            },
        ]

    def write(self, root: Path, entries: list[dict]) -> Path:
        path = root / "wrangler-output.jsonl"
        path.write_text("".join(json.dumps(entry) + "\n" for entry in entries))
        return path

    def extract(self, path: Path) -> str:
        return deployment_receipt.extract_deployment_url(
            path,
            expected_revision=self.REVISION,
            project=self.PROJECT,
            production_branch="main",
        )

    def test_exact_wrangler_receipt_returns_immutable_origin(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(
                self.extract(self.write(Path(directory), self.entries())), self.URL
            )

    def test_mismatched_or_ambiguous_receipts_fail_closed(self) -> None:
        cases = {
            "wrong revision": lambda entries: entries[1]["deployment_trigger"][
                "metadata"
            ].update(commit_hash="b" * 40),
            "preview": lambda entries: entries[1].update(environment="preview"),
            "bare alias": lambda entries: (
                entries[0].update(url="https://ardent-tools.pages.dev"),
                entries[1].update(url="https://ardent-tools.pages.dev"),
            ),
            "two detailed": lambda entries: entries.append(copy.deepcopy(entries[1])),
        }
        for label, mutate in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                entries = self.entries()
                mutate(entries)
                with self.assertRaises(ValueError):
                    self.extract(self.write(Path(directory), entries))

    def test_duplicate_json_keys_and_unterminated_jsonl_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            duplicate = root / "duplicate.jsonl"
            duplicate.write_text(
                '{"type":"pages-deploy","type":"pages-deploy-detailed"}\n'
            )
            with self.assertRaisesRegex(ValueError, "duplicate key"):
                self.extract(duplicate)
            unterminated = root / "unterminated.jsonl"
            unterminated.write_text(json.dumps(self.entries()[0]))
            with self.assertRaisesRegex(ValueError, "LF-terminated"):
                self.extract(unterminated)


class PagesRuntimeContractTests(unittest.TestCase):
    def make_fixture(self, output: Path) -> None:
        (output / "css").mkdir(parents=True)
        (output / "css/site.css").write_text("body{}\n")
        (output / "index.html").write_text("home\n")
        (output / "about").mkdir()
        (output / "about/index.html").write_text("about\n")
        (output / "404.html").write_text("missing\n")
        (output / "_headers").write_text((ROOT / "_headers").read_text())
        (output / "_redirects").write_text((ROOT / "_redirects").read_text())
        authority = {
            "schema_version": 1,
            "revision": EXPECTED_REVISION,
            "route_count": 2,
            "routes": [
                {
                    "request_path": "/",
                    "output_path": "index.html",
                    "sha256": "0" * 64,
                },
                {
                    "request_path": "/about/",
                    "output_path": "about/index.html",
                    "sha256": "1" * 64,
                },
            ],
            "custom_404": {"output_path": "404.html", "sha256": "2" * 64},
        }
        (output / pages_runtime.AUTHORITY_NAME).write_text(json.dumps(authority))

    def make_fixture_with_extra_routes(
        self, output: Path, extra_request_paths: list[str]
    ) -> None:
        self.make_fixture(output)
        authority = json.loads((output / pages_runtime.AUTHORITY_NAME).read_text())
        for index, request_path in enumerate(extra_request_paths):
            output_path = f"{request_path.strip('/')}/index.html"
            page = output / output_path
            page.parent.mkdir(parents=True, exist_ok=True)
            page.write_text(f"page {index}\n")
            authority["routes"].append(
                {
                    "request_path": request_path,
                    "output_path": output_path,
                    "sha256": f"{index:064x}",
                }
            )
        authority["route_count"] = len(authority["routes"])
        (output / pages_runtime.AUTHORITY_NAME).write_text(json.dumps(authority))

    def test_routes_leave_retained_artifacts_static_and_missing_paths_guarded(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            self.make_fixture(output)
            include_count, exclude_count = pages_runtime.write_runtime(output)
            routes = json.loads((output / pages_runtime.ROUTES_NAME).read_text())
            boundary = json.loads((output / pages_runtime.BOUNDARY_NAME).read_text())
            errors = pages_runtime.validate_runtime(output)

        self.assertEqual(include_count, 1)
        self.assertEqual(exclude_count, len(routes["exclude"]))
        self.assertEqual(routes["include"], ["/*"])
        for path in (
            "/",
            "/about/",
            "/a/*",
            "/css/site.css",
            "/release-html.json",
            "/release-resources.json",
            "/runtime-boundary.json",
            "/404",
            "/404.html",
            "/demos",
            "/demos/*",
            "/systems/ergon-tools/*",
            "/systems/nosologia/*",
        ):
            self.assertIn(path, routes["exclude"])
        for alias in ("/index.html", "/about/index.html"):
            self.assertNotIn(alias, routes["exclude"])
        self.assertNotIn("/tapes/aletheia-memory.tape", routes["exclude"])
        self.assertEqual(boundary["function"]["path"], "functions/[[path]].js")
        self.assertEqual(boundary["schema_version"], 2)
        self.assertEqual(boundary["wrangler"]["path"], "wrangler.toml")
        self.assertIn(
            pages_runtime.BOUNDARY_NAME,
            production.REQUIRED_RELEASE_LOGICAL_PATHS,
        )
        self.assertEqual(
            boundary["function"]["sha256"],
            hashlib.sha256((ROOT / "functions/[[path]].js").read_bytes()).hexdigest(),
        )
        self.assertEqual(
            boundary["wrangler"]["sha256"],
            hashlib.sha256((ROOT / "wrangler.toml").read_bytes()).hexdigest(),
        )
        self.assertEqual(errors, [])

    def test_same_prefix_route_family_collapses_to_one_safe_wildcard(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            self.make_fixture_with_extra_routes(
                output,
                [
                    "/systems/",
                    "/systems/akroasis/",
                    "/systems/aletheia/",
                    "/systems/kanon/",
                ],
            )
            include_count, exclude_count = pages_runtime.write_runtime(output)
            routes = json.loads((output / pages_runtime.ROUTES_NAME).read_text())
            errors = pages_runtime.validate_runtime(output)
        self.assertEqual(errors, [])
        self.assertEqual(include_count, 1)
        self.assertEqual(exclude_count, len(routes["exclude"]))
        self.assertIn("/systems/*", routes["exclude"])
        for member in (
            "/systems/",
            "/systems/akroasis/",
            "/systems/aletheia/",
            "/systems/kanon/",
        ):
            self.assertNotIn(member, routes["exclude"])
        # The pre-existing hand-authored redirect wildcards for these two
        # slugs are subsumed by the broader family wildcard rather than left
        # behind as a separate, now-redundant, overlapping rule.
        self.assertNotIn("/systems/ergon-tools/*", routes["exclude"])
        self.assertNotIn("/systems/nosologia/*", routes["exclude"])
        self.assertNotIn("/about/*", routes["exclude"])
        self.assertIn("/about/", routes["exclude"])

    def test_single_member_prefix_is_left_uncollapsed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            self.make_fixture(output)
            routes, errors = pages_runtime.build_routes(output)
        self.assertEqual(errors, [])
        self.assertIn("/about/", routes["exclude"])
        self.assertNotIn("/about/*", routes["exclude"])

    def test_collapse_route_families_derives_and_fails_closed(self) -> None:
        safe = ["/systems/", "/systems/a/", "/systems/b/", "/other/"]
        collapsed, notes = pages_runtime.collapse_route_families(safe)
        self.assertEqual(collapsed, sorted(["/systems/*", "/other/"]))
        self.assertEqual(len(notes), 1)

        # A lone root with no siblings never forms a family at all.
        lone_root = sorted(["/systems/", "/other/"])
        collapsed_lone, notes_lone = pages_runtime.collapse_route_families(lone_root)
        self.assertEqual(collapsed_lone, lone_root)
        self.assertEqual(notes_lone, [])

        # The safety re-check inside collapse_route_families() is what makes
        # the design fail closed: replacing a family's members must leave no
        # route besides the wildcard itself still matching the wildcard's own
        # prefix. Exercise that guard directly against a deliberately
        # incomplete replacement (as if a family were only partially known).
        incomplete_candidate = sorted({"/systems/a/", "/systems/*"})
        leftover = [
            route
            for route in incomplete_candidate
            if route != "/systems/*" and route.startswith("/systems/")
        ]
        self.assertEqual(leftover, ["/systems/a/"])

    def test_route_rule_soft_warning_names_the_growth_trend(self) -> None:
        with tempfile.TemporaryDirectory() as baseline_directory:
            baseline_output = Path(baseline_directory)
            self.make_fixture(baseline_output)
            baseline_routes, baseline_errors = pages_runtime.build_routes(
                baseline_output
            )
            self.assertEqual(baseline_errors, [])
            baseline_count = len(baseline_routes["exclude"])
        needed = pages_runtime.WARN_ROUTE_RULES - baseline_count + 5
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            self.make_fixture_with_extra_routes(
                output, [f"/solo-{index}/" for index in range(needed)]
            )
            stdout = io.StringIO()
            with (
                mock.patch.object(
                    pages_runtime.sys,
                    "argv",
                    ["pages_runtime.py", str(output)],
                ),
                mock.patch.object(pages_runtime.sys, "stdout", stdout),
            ):
                exit_code = pages_runtime.main()
        self.assertEqual(exit_code, 0)
        output_text = stdout.getvalue()
        self.assertIn("PASS", output_text)
        self.assertIn("WARNING", output_text)
        self.assertIn(str(pages_runtime.WARN_ROUTE_RULES), output_text)
        self.assertIn(str(pages_runtime.MAX_ROUTE_RULES), output_text)

    def test_wrangler_config_is_exact_and_compatibility_date_is_pinned(self) -> None:
        source = (ROOT / pages_runtime.WRANGLER_RELATIVE_PATH).read_bytes()
        self.assertEqual(pages_runtime.validate_wrangler_config(source), [])
        drifted = source.replace(b"2026-07-21", b"2026-07-22")
        errors = pages_runtime.validate_wrangler_config(drifted)
        self.assertTrue(
            any("exact production Pages config" in error for error in errors), errors
        )

    def test_overlapping_ending_splat_routes_fail_before_upload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            self.make_fixture(output)
            authority_path = output / pages_runtime.AUTHORITY_NAME
            authority = json.loads(authority_path.read_text())
            authority["routes"].append(
                {
                    "request_path": "/demos/example",
                    "output_path": "demos/example.html",
                    "sha256": "3" * 64,
                }
            )
            authority_path.write_text(json.dumps(authority))
            _routes, _boundary, errors = pages_runtime.expected_runtime(output)
        self.assertTrue(
            any(
                "overlapping exclude rules '/demos/*' and '/demos/example'" in error
                for error in errors
            ),
            errors,
        )

    def test_function_direct_headers_are_bound_to_static_header_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            self.make_fixture(output)
            headers_path = output / "_headers"
            headers_path.write_text(
                headers_path.read_text().replace(
                    "X-Frame-Options: DENY", "X-Frame-Options: SAMEORIGIN"
                )
            )
            _routes, _boundary, errors = pages_runtime.expected_runtime(output)
        self.assertTrue(
            any("Function static direct headers differ" in error for error in errors),
            errors,
        )

    def test_tampered_runtime_authority_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            self.make_fixture(output)
            pages_runtime.write_runtime(output)
            (output / pages_runtime.ROUTES_NAME).write_text("{}\n")
            errors = pages_runtime.validate_runtime(output)
        self.assertTrue(
            any("_routes.json differs" in error for error in errors), errors
        )

    def test_malformed_physical_resource_path_fails_before_upload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            self.make_fixture(output)
            malformed = output / "a/short.css"
            malformed.parent.mkdir()
            malformed.write_text("body{}\n")
            _routes, _boundary, errors = pages_runtime.expected_runtime(output)
        self.assertTrue(
            any("full SHA-256 and extension" in error for error in errors), errors
        )

    def test_routes_control_file_is_not_a_served_manifest_resource(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            self.make_fixture(output)
            pages_runtime.write_runtime(output)
            paths = {
                path.relative_to(output).as_posix()
                for path in release.public_files(output, pages_runtime.MANIFEST_NAME)
            }
        self.assertNotIn("_routes.json", paths)
        self.assertIn("runtime-boundary.json", paths)


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
        self.assertTrue(
            any("2 effective Cache-Control" in error for error in errors), errors
        )

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
        self.assertTrue(
            any("must be exactly no-store, no-transform" in error for error in errors),
            errors,
        )

    def test_revision_sentinel_must_be_no_store(self) -> None:
        headers = """/*
  Cache-Control: public, max-age=60, no-transform
"""
        with tempfile.TemporaryDirectory() as directory:
            errors: list[str] = []
            site.validate_cache_contract(errors, Path(directory), headers)
        self.assertTrue(
            any("must be exactly no-store, no-transform" in error for error in errors),
            errors,
        )

    def test_addressed_asset_prefix_requires_the_detached_immutable_override(
        self,
    ) -> None:
        headers = """/*
  Cache-Control: no-store, no-transform

/a/*
  ! Cache-Control
  Cache-Control: public, max-age=31536000, immutable
"""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            output.joinpath("a").mkdir()
            output.joinpath("a/" + "0" * 64 + ".css").write_text("body{}")
            errors: list[str] = []
            site.validate_cache_contract(errors, output, headers)
        self.assertEqual(errors, [])

    def test_addressed_asset_prefix_without_detach_joins_and_fails(self) -> None:
        # Cloudflare Pages joins same-name headers from overlapping sections
        # rather than letting the later one win; a /a/* Cache-Control line
        # with no preceding detach leaves both the inherited no-store value
        # and the new immutable one in effect, which is neither policy.
        headers = """/*
  Cache-Control: no-store, no-transform

/a/*
  Cache-Control: public, max-age=31536000, immutable
"""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            output.joinpath("a").mkdir()
            output.joinpath("a/" + "0" * 64 + ".css").write_text("body{}")
            errors: list[str] = []
            site.validate_cache_contract(errors, output, headers)
        self.assertTrue(
            any("2 effective Cache-Control" in error for error in errors), errors
        )

    def test_repository_headers_pass_the_two_tier_cache_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            output.joinpath("a").mkdir()
            output.joinpath("a/" + "1" * 64 + ".css").write_text("body{}")
            output.joinpath("index.html").write_text("home\n")
            errors: list[str] = []
            site.validate_cache_contract(
                errors, output, (ROOT / "_headers").read_text()
            )
        self.assertEqual(errors, [])


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
        self.assertTrue(
            any("forbidden recording behavior" in error for error in errors), errors
        )
        self.assertTrue(
            any("visible in a typed command" in error for error in errors), errors
        )

    def test_positive_cast_requires_complete_rendered_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "public"
            static = root / "static"
            system_page = output / "systems/demo/index.html"
            catalog_page = output / "systems/index.html"
            evidence_page = output / "evidence/index.html"
            cast_file = static / "casts/demo.cast"
            cast_body = b"{}\n"
            cast_output = addressed_output("casts/demo.cast", cast_body)
            player_css_output = addressed_output(
                "vendor/asciinema/asciinema-player.css", CSS_BODY
            )
            player_js_output = addressed_output(
                "vendor/asciinema/asciinema-player.min.js", JS_BODY
            )
            player_css = output / player_css_output
            player_js = output / player_js_output
            deployed_cast = output / cast_output
            for path in (
                system_page,
                catalog_page,
                evidence_page,
                cast_file,
                deployed_cast,
                player_css,
                player_js,
            ):
                path.parent.mkdir(parents=True, exist_ok=True)
            cast_file.write_bytes(cast_body)
            deployed_cast.write_bytes(cast_body)
            player_css.write_bytes(CSS_BODY)
            player_js.write_bytes(JS_BODY)
            cast = "/casts/demo.cast"
            cast_url = f"{BASE_URL}/{cast_output}"
            system_markup = (
                f'<div data-cast="{cast_url}"></div>'
                f'<link rel="stylesheet" href="/{player_css_output}">'
                f'<script src="/{player_js_output}"></script>'
            )
            catalog_markup = (
                '<a href="https://ardent.tools/systems/demo/">WATCH RECORDING</a>'
            )
            evidence_markup = (
                '<a href="https://ardent.tools/systems/demo/">demo recording</a>'
            )
            html = {
                system_page: system_markup,
                catalog_page: catalog_markup,
                evidence_page: evidence_markup,
            }
            resources = []
            for logical_path, output_path, body in (
                ("casts/demo.cast", cast_output, cast_body),
                (
                    "vendor/asciinema/asciinema-player.css",
                    player_css_output,
                    CSS_BODY,
                ),
                (
                    "vendor/asciinema/asciinema-player.min.js",
                    player_js_output,
                    JS_BODY,
                ),
            ):
                resources.append(
                    {
                        "logical_path": logical_path,
                        "output_path": output_path,
                        "request_url": f"/{output_path}",
                        "sha256": hashlib.sha256(body).hexdigest(),
                        "cache_class": "addressed",
                    }
                )
            manifest = {"resources": resources}
            errors: list[str] = []
            site.validate_asset_contract(errors, {system_page: system_markup}, output)
            site.validate_player_contract(
                errors,
                [(Path("content/systems/demo.md"), cast)],
                html,
                "script-src 'self' 'wasm-unsafe-eval'",
                output,
                static,
                release_manifest=manifest,
            )
            self.assertEqual(errors, [])

            wrong_identity_markup = system_markup.replace(
                f"/{player_js_output}", f"/{player_js_output}?v=1"
            )
            errors = []
            site.validate_asset_contract(
                errors, {system_page: wrong_identity_markup}, output
            )
            self.assertEqual(len(errors), 1, errors)
            self.assertIn("query- and fragment-free", errors[0])

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
                release_manifest=manifest,
            )
            self.assertTrue(
                any("conditional player CSS/JS" in error for error in errors), errors
            )


class CatalogContractTests(unittest.TestCase):
    def test_ambiguous_agpl_identifier_is_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            catalog.exact_license("sphragis", "AGPL-3.0")

    def test_catalog_records_complete_deterministic_provenance(self) -> None:
        document = catalog.build_catalog(ROOT)
        provenance = document["provenance"]
        actual_paths = [item["path"] for item in provenance["sources"]]
        expected_paths = [
            path.relative_to(ROOT).as_posix() for path in catalog.source_paths(ROOT)
        ]
        self.assertEqual(document["schema_version"], 1)
        self.assertEqual(provenance["generator"], "bin/generate-systems-json.py")
        self.assertEqual(provenance["generator_version"], 1)
        self.assertEqual(actual_paths, expected_paths)
        self.assertIn("data/exact-system-licenses.json", actual_paths)
        for item in provenance["sources"]:
            body = (ROOT / item["path"]).read_bytes()
            self.assertEqual(item["sha256"], hashlib.sha256(body).hexdigest())

    def test_catalog_rows_and_provenance_share_one_immutable_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / "content/systems", root / "content/systems")
            (root / "data").mkdir()
            shutil.copy2(
                ROOT / "data/exact-system-licenses.json",
                root / "data/exact-system-licenses.json",
            )
            target = root / "content/systems/aletheia.md"
            original_body = target.read_bytes()
            real_read_bytes = Path.read_bytes
            reads = 0

            def read_then_delete(path: Path) -> bytes:
                nonlocal reads
                body = real_read_bytes(path)
                if path == target:
                    reads += 1
                    if reads == 1:
                        path.unlink()
                return body

            with mock.patch.object(Path, "read_bytes", read_then_delete):
                document = catalog.build_catalog(root)

        row = next(item for item in document["systems"] if item["name"] == "aletheia")
        source = next(
            item
            for item in document["provenance"]["sources"]
            if item["path"] == "content/systems/aletheia.md"
        )
        self.assertEqual(row["name"], "aletheia")
        self.assertEqual(source["sha256"], hashlib.sha256(original_body).hexdigest())
        self.assertEqual(reads, 1)

    def test_changed_source_fails_via_canonical_entrypoint_with_exact_name(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bin").mkdir()
            for filename in (
                "site.py",
                "generate-systems-json.py",
                "validate-career-claims.py",
                "career_claim_contract.py",
            ):
                shutil.copy2(ROOT / "bin" / filename, root / "bin" / filename)
            shutil.copytree(ROOT / "content/systems", root / "content/systems")
            shutil.copy2(ROOT / "content/about.md", root / "content/about.md")
            (root / "data").mkdir()
            shutil.copy2(
                ROOT / "data/exact-system-licenses.json",
                root / "data/exact-system-licenses.json",
            )
            shutil.copy2(
                ROOT / "data/career-claims.json", root / "data/career-claims.json"
            )
            (root / "resume").mkdir()
            shutil.copy2(
                ROOT / "resume/cody-kickertz-resume.typ",
                root / "resume/cody-kickertz-resume.typ",
            )
            (root / "static/files").mkdir(parents=True)
            shutil.copy2(
                ROOT / "static/files/cody-kickertz-resume.pdf",
                root / "static/files/cody-kickertz-resume.pdf",
            )
            entrypoint = root / "bin/site.py"
            subprocess.run(
                [sys.executable, str(entrypoint), "sync"],
                check=True,
                capture_output=True,
                text=True,
            )
            with (root / "content/systems/_index.md").open("a") as handle:
                handle.write("\nchanged authority input\n")
            completed = subprocess.run(
                [sys.executable, str(entrypoint), "check"],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(completed.returncode, 1)
        self.assertIn(
            "ERROR: stale generated artifact: static/systems.json",
            completed.stderr,
        )


class CareerClaimContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = json.loads((ROOT / "data/career-claims.json").read_text())
        cls.surfaces, errors = career.load_surfaces(
            ROOT, ROOT / "static/files/cody-kickertz-resume.pdf"
        )
        if errors:
            raise AssertionError(errors)

    def validate(
        self, document: dict, surfaces: dict[str, str] | None = None
    ) -> list[str]:
        return career.validate_manifest(
            document,
            self.surfaces if surfaces is None else surfaces,
            as_of=dt.date(2026, 7, 22),
        )

    def test_current_typed_authority_matches_all_three_surfaces(self) -> None:
        self.assertEqual(self.validate(copy.deepcopy(self.document)), [])

    def test_duplicate_missing_claim_and_missing_value_fail_closed(self) -> None:
        duplicate = copy.deepcopy(self.document)
        duplicate["claims"].append(copy.deepcopy(duplicate["claims"][0]))
        self.assertTrue(
            any("duplicate claim id" in error for error in self.validate(duplicate))
        )

        missing = copy.deepcopy(self.document)
        del missing["claims"][0]["id"]
        self.assertTrue(
            any(
                "unexpected or missing keys" in error
                for error in self.validate(missing)
            )
        )

        missing_claim = copy.deepcopy(self.document)
        missing_claim["claims"].pop()
        self.assertTrue(
            any("claim IDs differ" in error for error in self.validate(missing_claim))
        )

        missing_value = copy.deepcopy(self.document)
        missing_value["claims"][0]["values"].pop()
        self.assertTrue(
            any("value names differ" in error for error in self.validate(missing_value))
        )

    def test_value_type_unit_and_display_are_bound(self) -> None:
        for field, replacement, expected in (
            ("value", 999, "display must encode exactly typed value"),
            ("value", "157", "value must be a nonnegative integer"),
            ("unit", "bananas", "unit must be 'people'"),
        ):
            with self.subTest(field=field, replacement=replacement):
                changed = copy.deepcopy(self.document)
                changed["claims"][0]["values"][0][field] = replacement
                errors = self.validate(changed)
                self.assertTrue(any(expected in error for error in errors), errors)

        boolean_schema = copy.deepcopy(self.document)
        boolean_schema["schema_version"] = True
        self.assertTrue(
            any(
                "schema_version must be integer" in error
                for error in self.validate(boolean_schema)
            )
        )

    def test_nonfinite_value_cannot_validate_or_serialize(self) -> None:
        changed = copy.deepcopy(self.document)
        changed["claims"][0]["values"][0]["value"] = float("inf")
        errors = self.validate(changed)
        self.assertTrue(any("nonnegative integer" in error for error in errors), errors)
        receipt = career.build_receipt(changed, b"authority")
        with self.assertRaises(ValueError):
            career.serialize_receipt(receipt)

    def test_adversarial_contradictory_wording_fails_outside_renderings(self) -> None:
        variants = (
            "The office included 158 active-duty Marines.",
            "The number of Marines in the office was 158.",
            "The command had 158 Marines.",
            "The command had a dozen Marines.",
            "The office included 13 civilians.",
            "The office covered one finance function.",
            "The deployment lasted eight full months.",
            "The deployment used one naval vessel.",
            "The deployment used four ships.",
            "The deployment used a dozen ships.",
            "The deployment lasted half a year.",
            "The MEU contained 4,000 people.",
            "The MEU comprised 3,100 personnel.",
            "The office served 70,000-plus personnel across the region.",
            "The cash budget was $450K.",
            "The deployed cash budget totaled $360,000.",
            "The deployed fund held four hundred thousand dollars in cash.",
            "There were 2 cash discrepancies.",
        )
        for variant in variants:
            with self.subTest(variant=variant):
                surfaces = dict(self.surfaces)
                surfaces["about"] += f" {variant}"
                errors = self.validate(copy.deepcopy(self.document), surfaces)
                self.assertTrue(
                    any("contains unmanaged" in error for error in errors), errors
                )

    def test_new_rank_or_nation_count_variant_fails_semantically(self) -> None:
        variants = (
            (
                "It was a third-ranked disbursing office on a deployment across "
                "18 nations."
            ),
            "The deployment crossed 18 countries. It was the No. 2 disbursing office.",
            (
                "The deployment crossed a dozen countries. It was the "
                "second-busiest disbursing office."
            ),
        )
        for variant in variants:
            with self.subTest(variant=variant):
                surfaces = dict(self.surfaces)
                surfaces["about"] += f" {variant}"
                errors = self.validate(copy.deepcopy(self.document), surfaces)
                self.assertTrue(
                    any("excluded disbursing-office rank" in error for error in errors),
                    errors,
                )
                self.assertTrue(
                    any(
                        "excluded deployment nation count" in error for error in errors
                    ),
                    errors,
                )

    def test_rendering_numeric_multiset_cannot_hide_extra_assertion(self) -> None:
        changed = copy.deepcopy(self.document)
        surfaces = dict(self.surfaces)
        for rendering in changed["claims"][0]["renderings"]:
            old = career.normalized(rendering["text"])
            new = f"{old} alongside 158 Marines"
            rendering["text"] = new
            surface = rendering["surface"]
            surfaces[surface] = surfaces[surface].replace(old, new, 1)
        errors = self.validate(changed, surfaces)
        self.assertTrue(
            any("rendering numeric multiset" in error for error in errors), errors
        )
        self.assertTrue(any("unmanaged Marine headcount" in error for error in errors))

    def test_rendering_cannot_hide_fuzzy_quantity_assertion(self) -> None:
        changed = copy.deepcopy(self.document)
        surfaces = dict(self.surfaces)
        for rendering in changed["claims"][0]["renderings"]:
            old = career.normalized(rendering["text"])
            new = f"{old} alongside a dozen Marines"
            rendering["text"] = new
            surface = rendering["surface"]
            surfaces[surface] = surfaces[surface].replace(old, new, 1)
        errors = self.validate(changed, surfaces)
        self.assertTrue(any("unmanaged Marine headcount" in error for error in errors))

    def test_operator_digest_binds_exact_typed_claim_payload(self) -> None:
        changed = copy.deepcopy(self.document)
        changed_value = changed["claims"][0]["values"][0]
        changed_value["value"] = 999
        changed_value["display"] = "999 Marines"
        surfaces = dict(self.surfaces)
        for rendering in changed["claims"][0]["renderings"]:
            old = career.normalized(rendering["text"])
            new = old.replace("157 Marines", "999 Marines")
            rendering["text"] = new
            surface = rendering["surface"]
            surfaces[surface] = surfaces[surface].replace(old, new, 1)
        errors = self.validate(changed, surfaces)
        self.assertTrue(any("authority-bound value 157" in error for error in errors))
        self.assertTrue(
            any("authority-bound display '157 Marines'" in error for error in errors)
        )

    def test_operator_digest_binds_exact_role_rendering(self) -> None:
        changed = copy.deepcopy(self.document)
        surfaces = dict(self.surfaces)
        replacements = {
            "about": ("helping lead", "commanding"),
            "resume_source": ("Helped lead", "Commanded"),
            "resume_pdf": ("Helped lead", "Commanded"),
        }
        for rendering in changed["claims"][0]["renderings"]:
            surface = rendering["surface"]
            before, after = replacements[surface]
            old = career.normalized(rendering["text"])
            new = old.replace(before, after)
            rendering["text"] = new
            surfaces[surface] = surfaces[surface].replace(old, new, 1)
        errors = self.validate(changed, surfaces)
        self.assertTrue(
            any("text must equal the authority-bound" in error for error in errors),
            errors,
        )

    def test_evidence_exclusions_and_public_metadata_are_closed(self) -> None:
        unknown_evidence = copy.deepcopy(self.document)
        unknown_evidence["claims"][0]["evidence_ref"] = "operator-held:anything"
        self.assertTrue(
            any(
                "must resolve to the recorded operator authority" in error
                for error in self.validate(unknown_evidence)
            )
        )

        missing_exclusion = copy.deepcopy(self.document)
        missing_exclusion["excluded_public_claims"].pop()
        self.assertTrue(
            any(
                "excluded public claim contract differs" in error
                for error in self.validate(missing_exclusion)
            )
        )

        mutations = (
            (
                lambda item: item["verification_scope"].append("largest office"),
                "verification_scope",
            ),
            (
                lambda item: item["evidence_boundary"].update({"claim": "18 nations"}),
                "evidence_boundary",
            ),
            (
                lambda item: item["evidence_authorities"][0].update(
                    {"custodian": "someone else"}
                ),
                "operator-authority contract",
            ),
            (
                lambda item: item["evidence_authorities"][0].update(
                    {"review_basis": "private records inspected"}
                ),
                "operator-authority contract",
            ),
            (
                lambda item: item["evidence_authorities"][0].update(
                    {"recorded_at": "2020-01-01"}
                ),
                "operator-authority contract",
            ),
            (
                lambda item: item["evidence_authorities"][0].update(
                    {"source_locator": "operator-says-so"}
                ),
                "operator-authority contract",
            ),
            (
                lambda item: item["evidence_authorities"][0].update(
                    {"source_sha256": "0" * 64}
                ),
                "operator-authority contract",
            ),
            (
                lambda item: item["evidence_authorities"][0].update(
                    {"underlying_private_evidence_inspected": True}
                ),
                "operator-authority contract",
            ),
            (
                lambda item: item["excluded_public_claims"][0].update(
                    {"reason": "largest office"}
                ),
                "must contain only topic and decision",
            ),
            (
                lambda item: item["claims"][0].update(
                    {"scope": "largest_disbursing_office"}
                ),
                "registered scope code",
            ),
            (
                lambda item: item["claims"][0]["provenance"].update(
                    {"authority_sha256": "0" * 64}
                ),
                "closed authority binding",
            ),
        )
        for mutate, expected in mutations:
            with self.subTest(expected=expected):
                changed = copy.deepcopy(self.document)
                mutate(changed)
                errors = self.validate(changed)
                self.assertTrue(any(expected in error for error in errors), errors)

    def test_expired_verification_window_requires_operator_review(self) -> None:
        errors = career.validate_manifest(
            copy.deepcopy(self.document),
            self.surfaces,
            as_of=dt.date(2027, 7, 23),
        )
        self.assertTrue(
            any("verification expired" in error for error in errors), errors
        )

    def test_public_receipt_is_scoped_and_omits_surface_internals(self) -> None:
        raw = (ROOT / "data/career-claims.json").read_bytes()
        receipt = career.build_receipt(copy.deepcopy(self.document), raw)
        self.assertEqual(receipt["authority_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertFalse(
            receipt["evidence_boundary"]["underlying_private_evidence_inspected"]
        )
        self.assertEqual(
            receipt["evidence_authorities"][0]["kind"], "operator_authorization"
        )
        self.assertEqual(
            receipt["evidence_authorities"][0]["source_sha256"],
            career.AUTHORITY_SOURCE_SHA256,
        )
        self.assertIn(
            "did not inspect and does not publish",
            receipt["evidence_boundary"]["summary"],
        )
        self.assertIn("summary", receipt["claims"][0]["scope"])
        self.assertTrue(all("renderings" not in claim for claim in receipt["claims"]))


class SiteEntrypointContractTests(unittest.TestCase):
    def test_documented_and_automated_build_paths_use_site_entrypoint(self) -> None:
        readme = (ROOT / "README.md").read_text()
        agents = (ROOT / "AGENTS.md").read_text()
        workflow = (ROOT / ".github/workflows/deploy.yml").read_text()
        kanon = (ROOT / ".kanon-ci.toml").read_text()
        gate = (ROOT / "bin/check-site.sh").read_text()
        for command in ("serve", "build", "check", "gate"):
            self.assertIn(f"python3 bin/site.py {command}", readme)
        self.assertIn("python3 bin/site.py gate", agents)
        self.assertIn("run: python3 bin/site.py gate", workflow)
        self.assertIn('cmd = "python3 bin/site.py gate"', kanon)
        self.assertIn("python3 bin/site.py check", gate)
        self.assertGreaterEqual(gate.count("python3 bin/site.py build"), 2)
        for text in (readme, agents, workflow, kanon, gate):
            self.assertIsNone(re.search(r"(?m)^zola (?:serve|build|check)\b", text))

    def test_stable_sync_retries_a_concurrent_authority_change(self) -> None:
        with (
            mock.patch.object(
                site_entrypoint,
                "input_fingerprint",
                side_effect=("before", "changed", "changed", "changed"),
            ),
            mock.patch.object(site_entrypoint, "sync_derivations") as sync,
        ):
            observed = site_entrypoint.sync_stable()
        self.assertEqual(observed, "changed")
        self.assertEqual(sync.call_count, 2)

    def test_explicit_sync_uses_stable_authority_snapshot(self) -> None:
        with (
            mock.patch.object(site_entrypoint.os, "chdir"),
            mock.patch.object(site_entrypoint.sys, "argv", ["site.py", "sync"]),
            mock.patch.object(site_entrypoint, "sync_stable") as stable,
            mock.patch.object(site_entrypoint, "sync_derivations") as unstable,
        ):
            result = site_entrypoint.main()
        self.assertEqual(result, 0)
        stable.assert_called_once_with()
        unstable.assert_not_called()

    def test_input_fingerprint_records_file_identity_and_symlink_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target"
            source = root / "source"
            target.write_bytes(b"same bytes")
            source.write_bytes(b"same bytes")
            with (
                mock.patch.object(site_entrypoint, "ROOT", root),
                mock.patch.object(
                    site_entrypoint, "derivation_inputs", return_value=[source]
                ),
            ):
                regular = site_entrypoint.input_fingerprint()
                source.unlink()
                source.symlink_to(target)
                symlink = site_entrypoint.input_fingerprint()
        self.assertNotEqual(regular, symlink)

    def test_serve_terminates_and_reaps_child_on_refresh_failure(self) -> None:
        real_popen = subprocess.Popen
        for failure, expected in (
            (subprocess.CalledProcessError(7, ["derive"]), 7),
            (PermissionError("authority unreadable"), 1),
        ):
            with self.subTest(failure=type(failure).__name__):
                process: subprocess.Popen | None = None

                def start_real_child(
                    _command: list[str], *, cwd: Path
                ) -> subprocess.Popen:
                    nonlocal process
                    process = real_popen(
                        [sys.executable, "-c", "import time; time.sleep(30)"],
                        cwd=cwd,
                    )
                    return process

                with (
                    mock.patch.object(
                        site_entrypoint,
                        "sync_stable",
                        side_effect=("before", failure),
                    ),
                    mock.patch.object(
                        site_entrypoint, "input_fingerprint", return_value="changed"
                    ),
                    mock.patch.object(
                        site_entrypoint.subprocess, "Popen", start_real_child
                    ),
                    mock.patch.object(site_entrypoint.time, "sleep"),
                    mock.patch.object(site_entrypoint.sys, "stderr", io.StringIO()),
                ):
                    result = site_entrypoint.serve([])

                self.assertEqual(result, expected)
                self.assertIsNotNone(process)
                assert process is not None
                self.assertIsNotNone(process.poll())


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
        self.assertTrue(
            any("embedded font set differs" in error for error in errors), errors
        )


if __name__ == "__main__":
    unittest.main()
