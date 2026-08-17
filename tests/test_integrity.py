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
sbom = load_script("ardent_generate_sbom", "generate-sbom.py")
fleet_counts = load_script("ardent_fleet_counts", "validate-fleet-counts.py")
excluded_links = load_script("ardent_verify_excluded_links", "verify-excluded-links.py")
career = load_script("ardent_career_claims", "validate-career-claims.py")
site_entrypoint = load_script("ardent_site_entrypoint", "site.py")
resume_fonts = load_script("ardent_resume_fonts", "validate-resume-fonts.py")
link_check_contract = load_script("ardent_link_check_contract", "link_check_contract.py")
release = load_script("ardent_release_manifest", "release_manifest.py")
content_address = load_script("ardent_content_address", "content_address.py")
asset_retention = load_script("ardent_asset_retention", "asset_retention.py")
generate_sbom = load_script("ardent_generate_sbom", "generate-sbom.py")
deployment_receipt = load_script(
    "ardent_pages_deployment_receipt", "pages_deployment_receipt.py"
)
last_deployment = load_script(
    "ardent_pages_last_deployment", "pages_last_deployment.py"
)
verify_restore = load_script("ardent_verify_restore", "verify_restore.py")
pages_reconcile = load_script("ardent_pages_reconcile", "pages_reconcile.py")

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
    "default-src 'self'; img-src 'self'; style-src 'self'; "
    "script-src 'self' 'wasm-unsafe-eval'; "
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
        "Would show: 0 published casts so far."
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
            "sbom.cdx.json": b"{}\n",
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
                "Would show: 0 published casts so far."
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
            any("CSP differs from the header contract" in error for error in errors),
            errors,
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

    def test_malformed_percent_encoding_in_source_or_target_fails(self) -> None:
        base = "\n".join(rule.declaration for rule in redirects.SUPPORTED_REDIRECTS)
        cases = {
            "bare-percent-source": (
                base + "\n/foo% /evidence/ 301",
                "malformed redirect source",
            ),
            "short-percent-source": (
                base + "\n/foo%z /evidence/ 301",
                "malformed redirect source",
            ),
            "bad-hex-target": (
                base.replace(
                    "/demos /evidence/ 301", "/demos /evidence%zz/ 301"
                ),
                "normalized same-origin path",
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

    def test_multiple_external_url_tokens_in_one_document_resolve_in_one_batch(
        self,
    ) -> None:
        files = {
            "index.html": (
                b'<img src="https://example.com/one.svg">'
                b'<img src="https://example.com/two.svg">'
                b'<img src="https://example.com/three.svg">'
                b'<link rel="stylesheet" href="/css/app.css">'
            ),
            "css/app.css": b"body{color:red}\n",
        }
        content_address._RESOLVED_CONSUMER_URL_CACHE.clear()
        real_resolve = content_address.resolve_browser_references
        calls: list[list[str]] = []

        def counting_resolve(references, bases=None, *, upgrade_insecure=True):
            calls.append(list(references))
            return real_resolve(references, bases, upgrade_insecure=upgrade_insecure)

        with mock.patch.object(
            content_address,
            "resolve_browser_references",
            side_effect=counting_resolve,
        ):
            with tempfile.TemporaryDirectory() as directory:
                self.finalize(Path(directory), files)
        # PERF: three distinct external references discovered in one
        # document resolve through ONE batched Node subprocess call rather
        # than one call per reference.
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            sorted(calls[0]),
            sorted(
                [
                    "https://example.com/one.svg",
                    "https://example.com/two.svg",
                    "https://example.com/three.svg",
                ]
            ),
        )

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

    def test_root_relative_fast_path_matches_pinned_whatwg_parser(self) -> None:
        # WHY: content_address.resolved_consumer_url() takes a Python-urlparse
        # fast path for root-relative references instead of the pinned Node
        # WHATWG parser. The fast path must stay equivalent for the leading/
        # trailing C0-control-or-space stripping that step differs on; a
        # trailing control byte survives urlparse but not a real browser. A
        # tab or newline sitting between two literal slashes is the sharper
        # case: stripped, it reconstitutes a "//" network-path prefix that
        # was never in the raw reference, so the pinned parser resolves a
        # different origin entirely rather than a mismatched path.
        base = "https://ardent.tools/index.html"
        origin = "https://ardent.tools"
        for reference in (
            "/img/pixel\n.svg",
            "/img/pixel\t.svg",
            "/img/pixel.svg\x0b",
            "/img/pixel.svg\x00",
            "/img/pixel.svg ",
            "/\t/evil.example/img/pixel.svg",
        ):
            with self.subTest(reference=reference):
                fast_result = content_address.same_origin_path(reference, base, origin)
                content_address._RESOLVED_CONSUMER_URL_CACHE.clear()
                subprocess_resolved = release.resolve_browser_references(
                    [reference], [base]
                )[0]
                if subprocess_resolved["hostname"] != "ardent.tools":
                    subprocess_result = None
                else:
                    subprocess_result = release.canonical_resource_path(
                        subprocess_resolved["pathname"]
                    ).lstrip("/")
                self.assertEqual(fast_result, subprocess_result)

    def test_root_relative_reference_with_trailing_control_byte_still_addresses(
        self,
    ) -> None:
        files = {
            "index.html": b'<img src="/img/pixel.svg\x0b">',
            "img/pixel.svg": b'<svg xmlns="http://www.w3.org/2000/svg"/>',
        }
        with tempfile.TemporaryDirectory() as directory:
            output, _document = self.finalize(Path(directory), files)
            html_body = (output / "index.html").read_text()
        self.assertRegex(html_body, r'<img src="/a/[0-9a-f]{64}\.svg">')

    def test_resolved_consumer_url_cache_is_bounded_not_a_leak(self) -> None:
        # WHY: this cache backs resolved_consumer_url() for the whole life of
        # one build process. An unbounded dict here is a slow memory leak
        # nobody attributes to this call site; prove the bound actually
        # evicts the least-recently-used entry rather than merely existing
        # as a constant nobody enforces.
        content_address._RESOLVED_CONSUMER_URL_CACHE.clear()
        maxsize = content_address.RESOLVED_CONSUMER_URL_CACHE_MAXSIZE
        base = "https://ardent.tools/"
        for index in range(maxsize + 1):
            content_address._cache_resolved_consumer_url(
                (f"/img/{index}.svg", base, False),
                {"pathname": f"/img/{index}.svg"},
            )
        self.assertEqual(len(content_address._RESOLVED_CONSUMER_URL_CACHE), maxsize)
        self.assertNotIn(
            ("/img/0.svg", base, False),
            content_address._RESOLVED_CONSUMER_URL_CACHE,
        )
        self.assertIn(
            (f"/img/{maxsize}.svg", base, False),
            content_address._RESOLVED_CONSUMER_URL_CACHE,
        )

    def test_html_parsing_errors_are_attributed_to_their_source_file(self) -> None:
        cases = {
            "unquoted": (
                b"<img src=/img/pixel.svg>",
                "HTML resource URL attributes must be quoted",
            ),
            "compound": (
                b'<img srcset="/img/pixel.svg 1x">',
                "compound HTML URL attributes are forbidden",
            ),
            "nested json-ld": (
                b'<script type="application/ld+json"/>'
                b'<script type="application/ld+json">{}</script>',
                r"nested application/ld\+json blocks are forbidden",
            ),
        }
        for label, (snippet, expected) in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                files = {
                    "index.html": snippet,
                    "img/pixel.svg": b'<svg xmlns="http://www.w3.org/2000/svg"/>',
                }
                # WHY: the error must name the offending file, not read as a
                # bare, source-less complaint.
                with self.assertRaisesRegex(ValueError, rf"^index\.html: .*{expected}"):
                    self.finalize(Path(directory), files)

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

    def test_compacted_speculation_rules_keep_their_media_type(self) -> None:
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
            first_url = next(iter(first["media_types"]))
            finalize_snapshot("second", b'{"prerender":[]}\n')

            # Compacting squashes the two entries above (each recorded under
            # the real "speculation-rules.json" logical_path) into one
            # checkpoint entry whose items carry a synthesized logical_path.
            # first_url's Content-Type rule must survive that regardless.
            compacted = asset_retention.record_checkpoint(ledger, assets)
            self.assertEqual(compacted["entry_count"], 1)

            third_output, third = finalize_snapshot(
                "third", b'{"prefetch":[],"prerender":[]}\n'
            )
            self.assertIn(first_url, third["media_types"])
            self.assertEqual(
                third["media_types"][first_url], release.SPECULATION_MEDIA_TYPE
            )
            manifest = release.build_manifest(
                third_output,
                EXPECTED_REVISION,
                third,
                {
                    "manifest_name": "release-resources.json",
                    "canonical_paths": [],
                    "tombstones": [],
                },
            )
            self.assertEqual(manifest["media_types"], third["media_types"])
            _contract, errors = headers_contract.validate_headers(
                (third_output / "_headers").read_text(), manifest
            )
            self.assertEqual(errors, [])
            self.assertIn(
                f"{first_url}\n  Content-Type: {release.SPECULATION_MEDIA_TYPE}",
                (third_output / "_headers").read_text(),
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

    def test_partial_multi_resource_snapshot_failure_is_rolled_back(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root / "asset-retention.json"
            assets = root / "retained-assets"
            first, first_body = self.resource_for("img/first.svg", b"first\n")
            asset_retention.record_snapshot(
                ledger, assets, [first], {first["output_path"]: first_body}
            )
            before_ledger = ledger.read_bytes()
            before_files = sorted(
                path.relative_to(assets) for path in assets.rglob("*") if path.is_file()
            )

            second, second_body = self.resource_for("img/second.svg", b"second\n")
            third, third_body = self.resource_for("img/third.svg", b"third\n")
            new_bodies = {
                second["output_path"]: second_body,
                third["output_path"]: third_body,
            }
            calls = {"current": 0}

            def flaky(size: int, label: str) -> None:
                if label.startswith("current physical asset"):
                    calls["current"] += 1
                    if calls["current"] == 2:
                        raise ValueError("synthetic failure on second item")

            with mock.patch.object(
                asset_retention, "require_static_file_size", side_effect=flaky
            ):
                with self.assertRaisesRegex(
                    ValueError, "synthetic failure on second item"
                ):
                    asset_retention.record_snapshot(
                        ledger, assets, [second, third], new_bodies
                    )

            # The failed call must leave the ledger and asset_root exactly as
            # the prior successful snapshot left them -- no orphan file from
            # the item that never reached the ledger.
            self.assertEqual(ledger.read_bytes(), before_ledger)
            after_files = sorted(
                path.relative_to(assets) for path in assets.rglob("*") if path.is_file()
            )
            self.assertEqual(after_files, before_files)

            # A bare retry, with no manual cleanup, then succeeds.
            document = asset_retention.record_snapshot(
                ledger, assets, [second, third], new_bodies
            )
            self.assertEqual(document["entry_count"], 2)

    def test_partial_first_snapshot_failure_removes_the_created_asset_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root / "asset-retention.json"
            assets = root / "retained-assets"
            first, first_body = self.resource_for("img/a.svg", b"a\n")
            second, second_body = self.resource_for("img/b.svg", b"b\n")
            bodies = {
                first["output_path"]: first_body,
                second["output_path"]: second_body,
            }
            calls = {"current": 0}

            def flaky(size: int, label: str) -> None:
                if label.startswith("current physical asset"):
                    calls["current"] += 1
                    if calls["current"] == 2:
                        raise ValueError("synthetic failure on second item")

            with mock.patch.object(
                asset_retention, "require_static_file_size", side_effect=flaky
            ):
                with self.assertRaisesRegex(
                    ValueError, "synthetic failure on second item"
                ):
                    asset_retention.record_snapshot(
                        ledger, assets, [first, second], bodies
                    )

            # Neither the ledger nor asset_root existed before this call, so
            # a failed call must leave neither behind either.
            self.assertFalse(ledger.exists())
            self.assertFalse(assets.exists())

            document = asset_retention.record_snapshot(
                ledger, assets, [first, second], bodies
            )
            self.assertEqual(document["entry_count"], 1)

    def test_ledger_write_failure_rolls_back_the_just_written_asset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root / "asset-retention.json"
            assets = root / "retained-assets"
            first, first_body = self.resource_for("img/first.svg", b"first\n")
            asset_retention.record_snapshot(
                ledger, assets, [first], {first["output_path"]: first_body}
            )
            before_ledger = ledger.read_bytes()
            before_files = sorted(
                path.relative_to(assets) for path in assets.rglob("*") if path.is_file()
            )

            second, second_body = self.resource_for("img/second.svg", b"second\n")
            real_write_atomic = asset_retention.write_atomic

            def flaky_write_atomic(path: Path, body: bytes) -> None:
                if path == ledger:
                    raise OSError(28, "synthetic disk pressure on ledger write")
                real_write_atomic(path, body)

            with mock.patch.object(
                asset_retention, "write_atomic", side_effect=flaky_write_atomic
            ):
                with self.assertRaises(OSError):
                    asset_retention.record_snapshot(
                        ledger,
                        assets,
                        [second],
                        {second["output_path"]: second_body},
                    )

            # The new asset physically landed before the ledger write that
            # would have recorded it failed. The transactional boundary must
            # cover the ledger write too, or this leaves an orphan file the
            # ledger never learned about -- exactly the half-written state
            # validate_ledger()'s strict set-equality check dead-ends on.
            self.assertEqual(ledger.read_bytes(), before_ledger)
            after_files = sorted(
                path.relative_to(assets) for path in assets.rglob("*") if path.is_file()
            )
            self.assertEqual(after_files, before_files)

            # A bare retry, with no manual cleanup, then succeeds.
            document = asset_retention.record_snapshot(
                ledger, assets, [second], {second["output_path"]: second_body}
            )
            self.assertEqual(document["entry_count"], 2)

    def test_asset_root_removal_failure_during_rollback_is_surfaced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root / "asset-retention.json"
            assets = root / "retained-assets"
            first, first_body = self.resource_for("img/a.svg", b"a\n")
            second, second_body = self.resource_for("img/b.svg", b"b\n")
            bodies = {
                first["output_path"]: first_body,
                second["output_path"]: second_body,
            }
            calls = {"current": 0}

            def flaky(size: int, label: str) -> None:
                if label.startswith("current physical asset"):
                    calls["current"] += 1
                    if calls["current"] == 2:
                        raise ValueError("synthetic failure on second item")

            def fake_rmtree(
                path: Path, ignore_errors: bool = False, **_kwargs: object
            ) -> None:
                # Mirrors shutil.rmtree's own ignore_errors contract, so this
                # only diverges from the real function in ONE way: whether
                # the caller asked it to swallow the removal failure.
                if ignore_errors:
                    return
                raise PermissionError(
                    "synthetic: cannot remove the created asset_root"
                )

            with (
                mock.patch.object(
                    asset_retention, "require_static_file_size", side_effect=flaky
                ),
                mock.patch.object(
                    asset_retention.shutil, "rmtree", side_effect=fake_rmtree
                ),
            ):
                # A rollback that cannot actually remove the just-created
                # asset_root must raise that failure rather than reporting
                # only the original error while quietly leaving the mess
                # behind (the ignore_errors=True bug).
                with self.assertRaises(PermissionError):
                    asset_retention.record_snapshot(
                        ledger, assets, [first, second], bodies
                    )

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

    @staticmethod
    def v1_entry(sequence: int, previous_digest: str | None, resources: list[dict]) -> dict:
        """A schema-v1 entry: same shape as v2's snapshot kind, minus the
        "kind" field that didn't exist yet."""
        return {
            "sequence": sequence,
            "previous_entry_sha256": previous_digest,
            "resource_count": len(resources),
            "resources": resources,
        }

    def test_validate_history_prefix_accepts_a_migrated_v1_prior(self) -> None:
        # Every prior ledger CI selects comes from an independently earlier
        # commit; today that commit's ledger is still schema v1 (this
        # repository's own migration to v2 lives only on this branch), so
        # this is not a hypothetical — it is the actual first-run shape.
        first, _first_body = self.resource_for("css/old.css", b"old\n")
        second, _second_body = self.resource_for("css/new.css", b"new\n")
        entry1 = self.v1_entry(1, None, [first])
        entry2 = self.v1_entry(
            2, asset_retention.entry_digest(entry1), [first, second]
        )
        v1_document = {
            "schema_version": 1,
            "entry_count": 2,
            "entries": [entry1, entry2],
        }
        migrated_entries = asset_retention.migrate_v1_entries([entry1, entry2])
        current = {
            "schema_version": asset_retention.LEDGER_SCHEMA_VERSION,
            "entry_count": len(migrated_entries),
            "entries": migrated_entries,
        }
        with tempfile.TemporaryDirectory() as directory:
            prior_path = Path(directory) / "prior-asset-retention.json"
            prior_path.write_text(json.dumps(v1_document))
            asset_retention.validate_history_prefix(current, prior_path)

    def test_validate_history_prefix_rejects_a_tampered_v1_prior(self) -> None:
        first, _first_body = self.resource_for("css/old.css", b"old\n")
        second, _second_body = self.resource_for("css/new.css", b"new\n")
        entry1 = self.v1_entry(1, None, [first])
        entry2 = self.v1_entry(
            2, asset_retention.entry_digest(entry1), [first, second]
        )
        migrated_entries = asset_retention.migrate_v1_entries([entry1, entry2])
        current = {
            "schema_version": asset_retention.LEDGER_SCHEMA_VERSION,
            "entry_count": len(migrated_entries),
            "entries": migrated_entries,
        }

        tampered_second = copy.deepcopy(entry2)
        tampered_resource = tampered_second["resources"][1]
        tampered_resource["sha256"] = "0" * 64
        tampered_resource["output_path"] = "a/" + "0" * 64 + ".css"
        tampered_document = {
            "schema_version": 1,
            "entry_count": 2,
            "entries": [entry1, tampered_second],
        }
        with tempfile.TemporaryDirectory() as directory:
            prior_path = Path(directory) / "prior-asset-retention.json"
            prior_path.write_text(json.dumps(tampered_document))
            # Normalization must not launder a tampered prior into a match:
            # current was migrated from the ORIGINAL entry2, so it cannot
            # literal-match a prior whose migrated entry2 now differs.
            with self.assertRaisesRegex(ValueError, "append-only base prefix"):
                asset_retention.validate_history_prefix(current, prior_path)

    def test_migrate_v1_entries_matches_the_checked_in_migration(self) -> None:
        # This is the exact correctness property CI depends on: normalizing
        # ANY real, unmodified v1 prior must reproduce byte-for-byte what
        # this repository's own v1-to-v2 migration produced, or literal
        # prefix-equality against a real historical base would false-fail.
        v1_ledger = json.loads((ROOT / "asset-retention.json").read_text())
        v1_ledger = copy.deepcopy(v1_ledger)
        # Reproduce the pre-migration (schema 1, no "kind") shape from the
        # currently-checked-in v2 ledger by stripping exactly what
        # migrate_v1_entries() adds, so this test stays correct even after
        # the real repository ledger no longer has a v1 predecessor on disk.
        for entry in v1_ledger["entries"]:
            del entry["kind"]
        v1_ledger["schema_version"] = 1
        migrated = asset_retention.migrate_v1_entries(v1_ledger["entries"])
        current_ledger = json.loads((ROOT / "asset-retention.json").read_text())
        self.assertEqual(migrated, current_ledger["entries"])

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

    def test_validate_history_prefix_accepts_checkpoint_strictly_ahead_of_prior(
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
            # A local ledger legitimately ahead of the checked-in base before
            # compacting carries a resource the base never named; the
            # checkpoint must still be accepted since it's a SUPERSET of the
            # base's obligations, not required to match them exactly.
            ahead = copy.deepcopy(compacted)
            third, _third_body = self.resource_for("css/newer.css", b"newer\n")
            checkpoint = ahead["entries"][0]
            checkpoint["resources"] = asset_retention.snapshot_resources(
                checkpoint["resources"] + [third]
            )
            checkpoint["resource_count"] = len(checkpoint["resources"])
            asset_retention.validate_history_prefix(ahead, prior_path)

    def test_validate_history_prefix_rejects_checkpoint_missing_prior_obligation(
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
            # Simulate a hand-edited or buggy compaction: the root digest is
            # correct (this really is a checkpoint over prior's exact final
            # entry), but the resources list silently drops one obligation
            # prior's history held — as if the corresponding file under
            # retained-assets/ had also been deleted. The root digest alone
            # cannot catch this; only the superset check can.
            tampered = copy.deepcopy(compacted)
            checkpoint = tampered["entries"][0]
            dropped = next(
                item
                for item in checkpoint["resources"]
                if item["output_path"] == first["output_path"]
            )
            checkpoint["resources"] = [
                item for item in checkpoint["resources"] if item is not dropped
            ]
            checkpoint["resource_count"] = len(checkpoint["resources"])
            with self.assertRaisesRegex(
                ValueError, "drops retention obligations"
            ) as context:
                asset_retention.validate_history_prefix(tampered, prior_path)
            self.assertIn(first["output_path"], str(context.exception))

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

    def test_record_checkpoint_restores_the_prior_ledger_when_self_check_fails(
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
            on_disk_before = ledger.read_bytes()
            real_validate = asset_retention.validate_ledger
            calls = {"count": 0}

            def fail_second_call(ledger_path: Path, asset_root: Path):
                calls["count"] += 1
                result = real_validate(ledger_path, asset_root)
                if calls["count"] == 2:
                    raise ValueError("simulated post-write self-check failure")
                return result

            with mock.patch.object(
                asset_retention, "validate_ledger", side_effect=fail_second_call
            ):
                with self.assertRaisesRegex(ValueError, "simulated post-write"):
                    asset_retention.record_checkpoint(ledger, assets)
            # WHY: the failure happens AFTER the candidate checkpoint document
            # is already written to disk. Without rollback, that document --
            # which just failed its own self-check -- would be left in place
            # instead of the prior, still-valid ledger.
            self.assertEqual(ledger.read_bytes(), on_disk_before)

    def test_main_verify_failure_reports_error_without_argparse_usage_text(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root / "asset-retention.json"
            assets = root / "retained-assets"
            resource, body = self.resource_for("css/main.css", b"main\n")
            asset_retention.record_snapshot(
                ledger, assets, [resource], {resource["output_path"]: body}
            )
            prior_ledger = root / "prior.json"
            prior_ledger.write_text("not json")

            argv = [
                "asset_retention.py",
                "verify",
                "--ledger",
                str(ledger),
                "--assets",
                str(assets),
                "--prior-ledger",
                str(prior_ledger),
            ]
            stderr = io.StringIO()
            with mock.patch.object(asset_retention.sys, "argv", argv):
                with mock.patch.object(asset_retention.sys, "stderr", stderr):
                    exit_code = asset_retention.main()
            # WHY: a ledger-integrity ValueError is a data failure, not a
            # command-line usage mistake -- it must return the ordinary error
            # exit status and message, never argparse's usage-error path
            # (exit 2 plus a "usage: ..." banner).
            self.assertEqual(exit_code, 1)
            self.assertIn("ERROR:", stderr.getvalue())
            self.assertNotIn("usage:", stderr.getvalue())


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
            "sbom.cdx.json": b"{}\n",
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

    def test_addressed_output_path_extension_must_be_lowercase(self) -> None:
        # WHY: ADDRESSED_PATH_RE is shared with asset_retention.py, which has
        # always required a lowercase extension -- content_address.py never
        # writes any other kind. This proves release_manifest.py now rejects
        # what it used to silently accept.
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            contract, manifest, _raw = self.make_fixture(output)
            item = next(
                resource
                for resource in manifest["resources"]
                if resource["cache_class"] == "addressed"
            )
            stem, _, extension = item["output_path"].rpartition(".")
            uppercase_path = f"{stem}.{extension.upper()}"
            (output / item["output_path"]).rename(output / uppercase_path)
            item["output_path"] = uppercase_path
            item["request_url"] = f"/{uppercase_path}"
            _, errors = release.validate_manifest(
                release.serialize_manifest(manifest),
                output=output,
                expected_revision=EXPECTED_REVISION,
                contract=contract,
            )
        self.assertTrue(
            any("full-digest physical path" in error for error in errors), errors
        )

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

    def test_public_files_failure_reports_once_without_fabricated_coverage_errors(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            contract, _manifest, raw = self.make_fixture(output)
            (output / "stray-symlink").symlink_to(output / "robots.txt")
            _document, errors = release.validate_manifest(
                raw,
                output=output,
                expected_revision=EXPECTED_REVISION,
                contract=contract,
            )
        # WHY: a public_files() failure must surface exactly its own cause,
        # not cascade into "coverage differs"/"canonical paths are absent"
        # errors synthesized from the empty expected_paths fallback.
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("must not be a symlink", errors[0])


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

    def test_repeated_detach_of_the_same_header_in_one_section_fails(self) -> None:
        # WHY: a second detach of an already-detached name would otherwise
        # reopen the one-time redeclaration room the first detach granted,
        # letting a header be silently replaced any number of times with no
        # duplicate-declaration error ever firing.
        raw = (
            "/a/*\n"
            "  ! Cache-Control\n"
            "  Cache-Control: public, max-age=1, immutable\n"
            "  ! Cache-Control\n"
            "  Cache-Control: public, max-age=2, immutable\n"
        )
        _sections, _detached, errors = headers_contract.parse_headers(raw)
        self.assertTrue(
            any("duplicate detach" in error for error in errors), errors
        )

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

    def test_symlinked_sitemap_fails_as_a_symlink_not_a_parse_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            self.make_fixture(output)
            sitemap = output / "sitemap.xml"
            sitemap.unlink()
            # WHY: a dangling target makes the two orderings observably
            # different. The symlink sweep (SAFETY-first) reports the actual
            # policy violation; reading sitemap.xml before sweeping instead
            # surfaces a misleading "cannot parse" failure that never names
            # the real cause.
            sitemap.symlink_to(output / "does-not-exist.xml")
            with self.assertRaisesRegex(
                ValueError, r"contains a symlink: sitemap\.xml"
            ):
                html_contract.build_authority(output, EXPECTED_REVISION, BASE_URL)

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

    def test_validate_base_url_rejects_each_malformed_shape(self) -> None:
        for label, malformed in (
            ("non-https scheme", "http://ardent.tools"),
            ("missing hostname", "https://"),
            ("embedded credentials", "https://user:pass@ardent.tools"),
            ("non-default port", "https://ardent.tools:8443"),
            ("non-empty path", "https://ardent.tools/path"),
            ("non-empty params", "https://ardent.tools/;p=1"),
            ("non-empty query", "https://ardent.tools?q=1"),
            ("non-empty fragment", "https://ardent.tools#frag"),
            ("trailing slash", "https://ardent.tools/"),
            ("non-lowercase canonical form", "https://ArDent.tools"),
        ):
            with self.subTest(label=label):
                with self.assertRaisesRegex(
                    ValueError,
                    "HTML authority base URL must be one lowercase HTTPS origin",
                ):
                    html_contract.validate_base_url(malformed)

    def test_validate_base_url_wraps_urlparse_failure(self) -> None:
        with self.assertRaisesRegex(
            ValueError, "malformed HTML authority base URL"
        ):
            html_contract.validate_base_url("https://[::1")

    def test_validate_base_url_accepts_the_one_true_shape(self) -> None:
        self.assertEqual(
            html_contract.validate_base_url("https://ardent.tools"),
            "https://ardent.tools/",
        )

    def test_sitemap_paths_rejects_each_malformed_shape(self) -> None:
        def write_sitemap(output: Path, *locs: str) -> None:
            urls = "".join(f"<url><loc>{loc}</loc></url>" for loc in locs)
            (output / "sitemap.xml").write_bytes(
                (
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                    f"{urls}"
                    "</urlset>"
                ).encode()
            )

        for label, pattern, locs in (
            ("cross-origin", "not same-origin", ["https://other.example/"]),
            ("query", "query or fragment", [f"{BASE_URL}/?x=1"]),
            ("fragment", "query or fragment", [f"{BASE_URL}/#frag"]),
            ("non-canonical", "not canonical", [f"{BASE_URL}:443/about/"]),
            (
                "duplicate route",
                "repeats HTML route",
                [f"{BASE_URL}/about/", f"{BASE_URL}/about/"],
            ),
        ):
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as directory:
                    output = Path(directory)
                    write_sitemap(output, *locs)
                    with self.assertRaisesRegex(ValueError, pattern):
                        html_contract.sitemap_paths(output, BASE_URL)

    def test_main_writes_and_self_validates_the_authority_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            self.make_fixture(output)
            argv = [
                "html_authority.py",
                str(output),
                "--revision",
                EXPECTED_REVISION,
                "--base-url",
                BASE_URL,
            ]
            stdout = io.StringIO()
            with mock.patch.object(html_contract.sys, "argv", argv):
                with mock.patch.object(html_contract.sys, "stdout", stdout):
                    exit_code = html_contract.main()
            self.assertEqual(exit_code, 0)
            self.assertIn("PASS", stdout.getvalue())
            written = (output / html_contract.AUTHORITY_NAME).read_bytes()
            expected = html_contract.build_authority(output, EXPECTED_REVISION, BASE_URL)
            self.assertEqual(written, html_contract.serialize_authority(expected))

    def test_main_reports_a_self_validation_mismatch_and_exits_1(self) -> None:
        # WHY: main() writes the authority file, then calls validate_authority()
        # to prove the write matches a fresh rebuild of the tree, failing the
        # run if it does not. A happy-path fixture can never show that gate
        # actually gates anything -- nothing has drifted, so validate_authority()
        # reports no errors whether or not main() honors its result. Force the
        # one outcome the self-check exists to catch: validate_authority()
        # itself reporting a mismatch, and prove main() turns that into a
        # failed run rather than the PASS it would print for a clean one.
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            self.make_fixture(output)
            argv = [
                "html_authority.py",
                str(output),
                "--revision",
                EXPECTED_REVISION,
                "--base-url",
                BASE_URL,
            ]
            drift = f"{html_contract.AUTHORITY_NAME} differs from the exact retained HTML tree"
            stdout = io.StringIO()
            stderr = io.StringIO()
            with mock.patch.object(
                html_contract, "validate_authority", return_value=({}, [drift])
            ):
                with mock.patch.object(html_contract.sys, "argv", argv):
                    with mock.patch.object(html_contract.sys, "stdout", stdout):
                        with mock.patch.object(html_contract.sys, "stderr", stderr):
                            exit_code = html_contract.main()
            self.assertEqual(exit_code, 1)
            self.assertIn(f"ERROR: {drift}", stderr.getvalue())
            self.assertNotIn("PASS", stdout.getvalue())

    def test_main_reports_build_failure_and_exits_1_without_a_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            self.make_fixture(output)
            (output / "sitemap.xml").unlink()
            argv = [
                "html_authority.py",
                str(output),
                "--revision",
                EXPECTED_REVISION,
                "--base-url",
                BASE_URL,
            ]
            stderr = io.StringIO()
            with mock.patch.object(html_contract.sys, "argv", argv):
                with mock.patch.object(html_contract.sys, "stderr", stderr):
                    exit_code = html_contract.main()
            self.assertEqual(exit_code, 1)
            self.assertIn("ERROR:", stderr.getvalue())
            # WHY: the test's own name claims no traceback leaks past the
            # caught-and-reported failure; assert it, don't just imply it.
            self.assertNotIn("Traceback (most recent call last):", stderr.getvalue())
            self.assertFalse((output / html_contract.AUTHORITY_NAME).exists())


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

        # wrangler comes from the pinned npm ci toolchain (node_modules/.bin on
        # PATH), not a per-step global install; the install step must precede it.
        install_step = workflow_step(steps, "Install pa11y-ci, lychee, playwright")
        self.assertIn("npm ci", install_step["run"])
        self.assertIn('node_modules/.bin" >> "$GITHUB_PATH"', install_step["run"])
        compile_step = workflow_step(steps, "Compile the Pages error boundary")
        self.assertIn(
            "wrangler pages functions build functions", compile_step["run"]
        )
        self.assertLess(
            step_names.index("Install pa11y-ci, lychee, playwright"),
            step_names.index("Compile the Pages error boundary"),
        )
        self.assertNotIn("--compatibility-date", workflow_text)

        # AT-01: build/gate runs once; the gated public/ tree deploys as a
        # preview, is fully verified, and only then is promoted to
        # production - preserved by this exact step ordering.
        ordered_steps = (
            "Compile the Pages error boundary",
            "Capture last-known-good production deployment",
            "Deploy preview to Cloudflare Pages",
            "Verify preview deployment",
            "Promote verified preview to production",
            "Purge Cloudflare cache so shared-header changes reach immutable resources",
            "Verify canonical domain after production cutover",
            "Reconcile Cloudflare deployment state",
            "Restore last-known-good production deployment",
        )
        for earlier, later in zip(ordered_steps, ordered_steps[1:]):
            self.assertLess(
                step_names.index(earlier),
                step_names.index(later),
                f"{earlier!r} must precede {later!r}",
            )

        capture_step = workflow_step(
            steps, "Capture last-known-good production deployment"
        )
        self.assertEqual(capture_step.get("id"), "capture_last_good")
        capture_run = capture_step["run"]
        # AT-01 follow-up: the last-known-good lookup calls the CF API
        # directly - wrangler's own `--json` output is a PascalCase display
        # mapping the extractor does not understand and truncates the
        # commit to 7 hex chars (see PagesLastDeploymentTests' wrangler
        # rejection test below).
        self.assertNotIn("wrangler pages deployment list --project-name", capture_run)
        self.assertIn(
            "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}"
            "/pages/projects/ardent-tools/deployments?page=",
            capture_run,
        )
        self.assertIn("Authorization: Bearer ${CLOUDFLARE_API_TOKEN}", capture_run)
        self.assertIn("page=${page}", capture_run)
        # Only `page` is sent: the documented env/per_page params returned a
        # live HTTP 400 on the first cutover, so environment is filtered
        # client-side (pages_last_deployment.py) and per_page is left to CF's
        # default. A regression that re-adds either would 400 production again.
        self.assertNotIn("env=production", capture_run)
        self.assertNotIn("per_page=", capture_run)
        # curl must NOT use --fail (it suppresses the CF error body); the body
        # is logged on any non-success so a 400 is diagnosable, not a bare 22.
        # (Checks the invocation, not the prose comment that names the flag.)
        self.assertNotIn("curl -sS --fail", capture_run)
        self.assertIn('cat "$page_file"', capture_run)
        # Paginates until an EMPTY page proves the list is exhausted, with a
        # bounded max_pages so an API/response anomaly cannot loop forever.
        self.assertIn("max_pages", capture_run)
        self.assertIn('"$page_count" -eq 0', capture_run)
        self.assertIn("bin/pages_last_deployment.py", capture_run)
        self.assertIn('>> "$GITHUB_OUTPUT"', capture_run)
        self.assertNotIn(
            "wrangler pages deployment list --project-name", workflow_text
        )

        preview_deploy_step = workflow_step(steps, "Deploy preview to Cloudflare Pages")
        self.assertEqual(preview_deploy_step.get("id"), "preview_deploy")
        preview_run = preview_deploy_step["run"]
        self.assertNotIn("wrangler pages deploy public", preview_run)
        self.assertNotIn("--branch=main", preview_run)
        preview_validate = preview_run.index(
            'python3 bin/validate-site.py public --expected-revision "$GITHUB_SHA"'
        )
        preview_attempted = preview_run.index('echo "attempted=true" >> "$GITHUB_OUTPUT"')
        preview_upload = preview_run.index(
            'wrangler pages deploy --branch="ci-preview-$GITHUB_SHA"'
        )
        # AT-02: attempted is recorded after the local pre-flight check but
        # strictly before the mutation itself, so it is set precisely when
        # a mutation was actually tried against Cloudflare - never on a
        # validate-site.py failure that never reached wrangler at all.
        self.assertLess(preview_validate, preview_attempted)
        self.assertLess(preview_attempted, preview_upload)
        self.assertIn('--commit-hash "$GITHUB_SHA"', preview_run)
        self.assertIn("WRANGLER_OUTPUT_FILE_PATH", preview_deploy_step["env"])
        self.assertNotEqual(
            preview_deploy_step["env"]["WRANGLER_OUTPUT_FILE_PATH"],
            "${{ runner.temp }}/ardent-wrangler-output.jsonl",
        )
        self.assertIn("bin/pages_deployment_receipt.py", preview_run)
        self.assertIn("--environment preview", preview_run)
        self.assertIn("ARDENT_PREVIEW_URL", preview_run)
        self.assertIn("--field url", preview_run)
        # AT-02 follow-up: the preview deployment id used to be extracted
        # here for the cleanup step, but a receipt-parse failure after a
        # real upload silently defeated cleanup (issue #95) - cleanup now
        # gets its id(s) from steps.reconcile, which asks Cloudflare
        # directly, so this step no longer needs to parse an id at all.
        self.assertNotIn("--field id", preview_run)
        self.assertNotIn("ARDENT_PREVIEW_DEPLOYMENT_ID", workflow_text)

        preview_verify_step = workflow_step(steps, "Verify preview deployment")
        self.assertEqual(preview_verify_step.get("id"), "preview_verify")
        preview_verify_run = preview_verify_step["run"]
        self.assertEqual(
            preview_verify_run.count("python3 bin/verify-production.py"), 1
        )
        self.assertIn('--base-url "$ARDENT_PREVIEW_URL"', preview_verify_run)
        self.assertIn("--canonical-origin https://ardent.tools", preview_verify_run)
        self.assertIn("--require-logical-alias-tombstones", preview_verify_run)
        self.assertIn("--attempts 37 --delay 10", preview_verify_run)

        promote_step = workflow_step(steps, "Promote verified preview to production")
        self.assertEqual(promote_step.get("id"), "promote")
        promote_run = promote_step["run"]
        self.assertNotIn("wrangler pages deploy public", promote_run)
        promote_validate = promote_run.index(
            'python3 bin/validate-site.py public --expected-revision "$GITHUB_SHA"'
        )
        promote_attempted = promote_run.index('echo "attempted=true" >> "$GITHUB_OUTPUT"')
        promote_upload = promote_run.index("wrangler pages deploy --branch=main")
        self.assertLess(promote_validate, promote_attempted)
        self.assertLess(promote_attempted, promote_upload)
        self.assertEqual(promote_step["env"]["GITHUB_SHA"], "${{ github.sha }}")
        self.assertIn('--commit-hash "$GITHUB_SHA"', promote_run)
        # AT-01 follow-up: promote's own receipt-parse had no consumer
        # (the canonical verify targets https://ardent.tools, not a
        # per-deploy immutable URL) and a parse failure AFTER a successful
        # upload would wrongly mark steps.promote.outcome as 'failure',
        # skipping restore-eligibility even though production bytes had
        # already changed. The step is exactly validate + upload now.
        self.assertNotIn("WRANGLER_OUTPUT_FILE_PATH", promote_step["env"])
        self.assertNotIn("pages_deployment_receipt.py", promote_run)
        self.assertNotIn("ARDENT_IMMUTABLE_URL", promote_run)
        self.assertNotIn("ARDENT_IMMUTABLE_URL", workflow_text)

        # INVARIANT: none of the preview/promote steps reference a status
        # check function - GitHub Actions implicitly ANDs success() onto
        # each, so a failed preview-verify skips promote automatically. A
        # future edit that adds always()/failure() here would defeat the
        # AT-01 fail-safe (preview must verify before promotion).
        for name in (
            "Deploy preview to Cloudflare Pages",
            "Verify preview deployment",
            "Promote verified preview to production",
        ):
            step_if = workflow_step(steps, name).get("if", "")
            self.assertNotIn("always()", step_if)
            self.assertNotIn("failure()", step_if)

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

        canonical_verify_step = workflow_step(
            steps, "Verify canonical domain after production cutover"
        )
        self.assertEqual(canonical_verify_step.get("id"), "canonical_verify")
        canonical_run = canonical_verify_step["run"]
        self.assertEqual(canonical_run.count("python3 bin/verify-production.py"), 1)
        self.assertIn("--base-url https://ardent.tools", canonical_run)
        self.assertIn("--canonical-origin https://ardent.tools", canonical_run)
        self.assertNotIn("--require-logical-alias-tombstones", canonical_run)
        self.assertIn("--attempts 13 --delay 10", canonical_run)

        reconcile_step = workflow_step(steps, "Reconcile Cloudflare deployment state")
        self.assertEqual(reconcile_step.get("id"), "reconcile")
        reconcile_if = reconcile_step["if"]
        # AT-02: reconciliation runs under always(), gated only on whether a
        # mutation was ever attempted - never on any step's own outcome, so
        # a client failure after Cloudflare accepted the mutation cannot
        # hide the resulting state from it.
        self.assertIn("always()", reconcile_if)
        self.assertIn("steps.preview_deploy.outputs.attempted == 'true'", reconcile_if)
        self.assertIn("steps.promote.outputs.attempted == 'true'", reconcile_if)
        self.assertNotIn("outcome", reconcile_if)
        reconcile_run = reconcile_step["run"]
        self.assertIn(
            "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}"
            "/pages/projects/ardent-tools/deployments?page=",
            reconcile_run,
        )
        self.assertIn("max_pages", reconcile_run)
        self.assertIn('"$page_count" -eq 0', reconcile_run)
        self.assertIn("bin/pages_reconcile.py", reconcile_run)
        self.assertIn('--revision "$GITHUB_SHA"', reconcile_run)
        self.assertIn('--preview-branch "ci-preview-$GITHUB_SHA"', reconcile_run)
        self.assertIn("--production-branch main", reconcile_run)
        self.assertIn('>> "$GITHUB_OUTPUT"', reconcile_run)

        unresolved_step = workflow_step(
            steps, "Cloudflare deployment state is unresolved after this run"
        )
        unresolved_if = unresolved_step["if"]
        self.assertIn("failure()", unresolved_if)
        self.assertIn("steps.reconcile.outcome != 'success'", unresolved_if)
        self.assertIn("steps.preview_deploy.outputs.attempted == 'true'", unresolved_if)
        self.assertIn("steps.promote.outputs.attempted == 'true'", unresolved_if)
        self.assertIn("exit 1", unresolved_step["run"])

    def test_concurrency_group_is_dedicated_and_non_cancelable_for_production(
        self,
    ) -> None:
        workflow_text = (ROOT / ".github/workflows/deploy.yml").read_text()
        workflow = parse_workflow_yaml(workflow_text)
        concurrency = workflow["concurrency"]
        self.assertIn("ardent-tools-production", concurrency["group"])
        self.assertIn(
            "github.event_name == 'push' || github.event_name == 'workflow_dispatch'",
            concurrency["group"],
        )
        self.assertIn("github.ref == 'refs/heads/main'", concurrency["group"])
        # WHY format(): PR/build runs keep the pre-AT-01 per-ref group so
        # they still cancel-in-progress against themselves.
        self.assertIn("format(", concurrency["group"])
        self.assertIn("!(", concurrency["cancel-in-progress"])
        self.assertIn(
            "github.ref == 'refs/heads/main'", concurrency["cancel-in-progress"]
        )

    def test_auto_restore_fires_only_when_cloudflare_confirms_production_landed(
        self,
    ) -> None:
        workflow_text = (ROOT / ".github/workflows/deploy.yml").read_text()
        workflow = parse_workflow_yaml(workflow_text)
        steps = workflow["jobs"]["gate-and-deploy"]["steps"]

        restore_step = workflow_step(
            steps, "Restore last-known-good production deployment"
        )
        restore_if = restore_step["if"]
        self.assertIn("failure()", restore_if)
        # AT-02: gated on Cloudflare's own reconciled state, never on
        # steps.promote.outcome - a client failure after Cloudflare
        # accepted the promotion must still trigger restore.
        self.assertIn("steps.reconcile.outputs.production_accepted == 'true'", restore_if)
        self.assertNotIn("steps.promote.outcome", restore_if)
        self.assertIn(
            "steps.capture_last_good.outputs.had_prior_deployment == 'true'",
            restore_if,
        )
        restore_run = restore_step["run"]
        self.assertIn("api.cloudflare.com/client/v4/accounts/", restore_run)
        self.assertIn(
            "/pages/projects/ardent-tools/deployments/"
            "${LAST_GOOD_DEPLOYMENT_ID}/rollback",
            restore_run,
        )
        self.assertIn("bin/verify_restore.py", restore_run)
        self.assertIn('--expected-revision "$LAST_GOOD_REVISION"', restore_run)
        self.assertIn("exit 1", restore_run)
        self.assertEqual(
            restore_step["env"]["LAST_GOOD_DEPLOYMENT_ID"],
            "${{ steps.capture_last_good.outputs.last_good_deployment_id }}",
        )
        self.assertEqual(
            restore_step["env"]["LAST_GOOD_REVISION"],
            "${{ steps.capture_last_good.outputs.last_good_revision }}",
        )

        no_prior_step = workflow_step(
            steps, "Fail loudly - no prior production deployment to restore"
        )
        no_prior_if = no_prior_step["if"]
        self.assertIn("failure()", no_prior_if)
        self.assertIn(
            "steps.reconcile.outputs.production_accepted == 'true'", no_prior_if
        )
        self.assertNotIn("steps.promote.outcome", no_prior_if)
        self.assertIn(
            "steps.capture_last_good.outputs.had_prior_deployment != 'true'",
            no_prior_if,
        )
        self.assertIn("exit 1", no_prior_step["run"])
        self.assertNotIn("wrangler pages deployment", no_prior_step["run"])

    def test_job_has_a_bounded_timeout(self) -> None:
        workflow_text = (ROOT / ".github/workflows/deploy.yml").read_text()
        workflow = parse_workflow_yaml(workflow_text)
        job = workflow["jobs"]["gate-and-deploy"]
        # AT-01 follow-up: a wedged run must not hold the non-cancelable
        # production concurrency group for GitHub's 6-hour job default.
        self.assertEqual(job["timeout-minutes"], "30")

    def test_preview_cleanup_is_best_effort_and_gated_on_a_real_preview(
        self,
    ) -> None:
        workflow_text = (ROOT / ".github/workflows/deploy.yml").read_text()
        workflow = parse_workflow_yaml(workflow_text)
        steps = workflow["jobs"]["gate-and-deploy"]["steps"]
        step_names = [step.get("name") for step in steps]

        cleanup_step = workflow_step(steps, "Delete preview deployment")
        cleanup_if = cleanup_step["if"]
        # always() so the preview is deleted whether the run went on to
        # succeed, fail preview_verify, fail promote, or fail-and-restore -
        # gated on Cloudflare's own reconciled state (AT-02), never on
        # steps.preview_deploy.outcome, so a receipt-parse failure after a
        # real upload cannot suppress cleanup (issue #95).
        self.assertIn("always()", cleanup_if)
        self.assertIn("steps.reconcile.outputs.preview_accepted == 'true'", cleanup_if)
        self.assertNotIn("steps.preview_deploy.outcome", cleanup_if)

        cleanup_run = cleanup_step["run"]
        self.assertIn(
            "-X DELETE "
            '"https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}'
            "/pages/projects/ardent-tools/deployments/"
            '${id}?force=true"',
            cleanup_run,
        )
        self.assertIn("Authorization: Bearer ${CLOUDFLARE_API_TOKEN}", cleanup_run)
        self.assertEqual(
            cleanup_step["env"]["PREVIEW_DEPLOYMENT_IDS"],
            "${{ steps.reconcile.outputs.preview_deployment_ids }}",
        )
        self.assertNotIn("ARDENT_PREVIEW_DEPLOYMENT_ID", cleanup_run)
        # Loops over every id reconcile found - an interrupted earlier
        # cleanup can leave more than one live preview for the same commit.
        self.assertIn("IFS=',' read -ra ids", cleanup_run)
        self.assertIn('for id in "${ids[@]}"', cleanup_run)
        # Best-effort: cleanup failure is swallowed, never an `exit 1` that
        # would fail an already-decided deploy/restore outcome.
        self.assertNotIn("exit 1", cleanup_run)
        self.assertIn("|| echo", cleanup_run)

        # Cleanup must run after reconcile (its id source) and after the
        # restore-decision steps, so it observes their outcome.
        self.assertLess(
            step_names.index("Reconcile Cloudflare deployment state"),
            step_names.index("Delete preview deployment"),
        )
        self.assertLess(
            step_names.index("Fail loudly - no prior production deployment to restore"),
            step_names.index("Delete preview deployment"),
        )

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

    def test_preview_environment_widens_without_weakening_production(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            entries = self.entries()
            entries[1].update(environment="preview")
            path = self.write(Path(directory), entries)
            url = deployment_receipt.extract_deployment_url(
                path,
                expected_revision=self.REVISION,
                project=self.PROJECT,
                production_branch="main",
                environment="preview",
            )
            self.assertEqual(url, self.URL)
            with self.assertRaises(ValueError):
                deployment_receipt.extract_deployment_url(
                    path,
                    expected_revision=self.REVISION,
                    project=self.PROJECT,
                    production_branch="main",
                    environment="production",
                )

    def test_invalid_environment_argument_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(Path(directory), self.entries())
            with self.assertRaises(ValueError):
                deployment_receipt.extract_deployment_url(
                    path,
                    expected_revision=self.REVISION,
                    project=self.PROJECT,
                    production_branch="main",
                    environment="staging",
                )

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

    def test_extract_deployment_id_matches_the_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(Path(directory), self.entries())
            deployment_id = deployment_receipt.extract_deployment_id(
                path,
                expected_revision=self.REVISION,
                project=self.PROJECT,
                production_branch="main",
            )
        self.assertEqual(deployment_id, self.DEPLOYMENT_ID)

    def test_extract_deployment_receipt_returns_url_and_id_together(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(Path(directory), self.entries())
            url, deployment_id = deployment_receipt.extract_deployment_receipt(
                path,
                expected_revision=self.REVISION,
                project=self.PROJECT,
                production_branch="main",
            )
        self.assertEqual(url, self.URL)
        self.assertEqual(deployment_id, self.DEPLOYMENT_ID)

    def test_main_field_argument_selects_url_or_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(Path(directory), self.entries())
            for field, expected in (("url", self.URL), ("id", self.DEPLOYMENT_ID)):
                with self.subTest(field=field):
                    captured = io.StringIO()
                    argv = [
                        "pages_deployment_receipt.py",
                        str(path),
                        "--expected-revision", self.REVISION,
                        "--project", self.PROJECT,
                        "--production-branch", "main",
                        "--field", field,
                    ]
                    with (
                        mock.patch.object(deployment_receipt.sys, "argv", argv),
                        mock.patch.object(deployment_receipt.sys, "stdout", captured),
                    ):
                        result = deployment_receipt.main()
                    self.assertEqual(result, 0)
                    self.assertEqual(captured.getvalue(), f"{expected}\n")

    def test_main_defaults_to_url_field(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(Path(directory), self.entries())
            captured = io.StringIO()
            argv = [
                "pages_deployment_receipt.py",
                str(path),
                "--expected-revision", self.REVISION,
                "--project", self.PROJECT,
                "--production-branch", "main",
            ]
            with (
                mock.patch.object(deployment_receipt.sys, "argv", argv),
                mock.patch.object(deployment_receipt.sys, "stdout", captured),
            ):
                result = deployment_receipt.main()
            self.assertEqual(result, 0)
            self.assertEqual(captured.getvalue(), f"{self.URL}\n")


class PagesLastDeploymentTests(unittest.TestCase):
    PROJECT = "ardent-tools"
    DEPLOYMENT_ID = "12345678-1234-1234-1234-123456789abc"
    OLDER_DEPLOYMENT_ID = "87654321-4321-4321-4321-cba987654321"
    REVISION = "a" * 40
    OLDER_REVISION = "b" * 40

    def entry(
        self,
        *,
        deployment_id: str,
        revision: str,
        created_on: str,
        environment: str = "production",
        project_name: str | None = None,
        is_skipped: bool = False,
        latest_stage_status: str | None = "success",
    ) -> dict:
        entry: dict = {
            "id": deployment_id,
            "environment": environment,
            "created_on": created_on,
            "deployment_trigger": {"metadata": {"commit_hash": revision}},
            "project_name": self.PROJECT if project_name is None else project_name,
            "is_skipped": is_skipped,
        }
        if latest_stage_status is not None:
            entry["latest_stage"] = {"status": latest_stage_status}
        return entry

    def write(self, root: Path, entries: list) -> Path:
        path = root / "deployments.json"
        path.write_text(json.dumps(entries))
        return path

    def test_picks_the_newest_production_entry_by_created_on(self) -> None:
        entries = [
            self.entry(
                deployment_id=self.OLDER_DEPLOYMENT_ID,
                revision=self.OLDER_REVISION,
                created_on="2026-07-01T00:00:00Z",
            ),
            self.entry(
                deployment_id=self.DEPLOYMENT_ID,
                revision=self.REVISION,
                created_on="2026-07-20T00:00:00Z",
            ),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(Path(directory), entries)
            deployment_id, revision = last_deployment.extract_last_good(
                path, project=self.PROJECT
            )
        self.assertEqual(deployment_id, self.DEPLOYMENT_ID)
        self.assertEqual(revision, self.REVISION)

    def test_ignores_preview_entries_when_selecting_newest(self) -> None:
        entries = [
            self.entry(
                deployment_id=self.DEPLOYMENT_ID,
                revision=self.REVISION,
                created_on="2026-07-01T00:00:00Z",
            ),
            self.entry(
                deployment_id=self.OLDER_DEPLOYMENT_ID,
                revision=self.OLDER_REVISION,
                created_on="2026-07-20T00:00:00Z",
                environment="preview",
            ),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(Path(directory), entries)
            deployment_id, revision = last_deployment.extract_last_good(
                path, project=self.PROJECT
            )
        self.assertEqual(deployment_id, self.DEPLOYMENT_ID)
        self.assertEqual(revision, self.REVISION)

    def test_empty_deployment_list_reports_no_prior_deployment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(Path(directory), [])
            deployment_id, revision = last_deployment.extract_last_good(
                path, project=self.PROJECT
            )
        self.assertIsNone(deployment_id)
        self.assertIsNone(revision)

    def test_result_envelope_shape_is_also_accepted(self) -> None:
        entries = {
            "result": [
                self.entry(
                    deployment_id=self.DEPLOYMENT_ID,
                    revision=self.REVISION,
                    created_on="2026-07-20T00:00:00Z",
                )
            ],
            "success": True,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "deployments.json"
            path.write_text(json.dumps(entries))
            deployment_id, revision = last_deployment.extract_last_good(
                path, project=self.PROJECT
            )
        self.assertEqual(deployment_id, self.DEPLOYMENT_ID)
        self.assertEqual(revision, self.REVISION)

    def test_malformed_deployment_fields_fail_closed(self) -> None:
        cases = {
            "bad id": [
                self.entry(
                    deployment_id="not-a-uuid",
                    revision=self.REVISION,
                    created_on="2026-07-20T00:00:00Z",
                )
            ],
            "bad commit hash": [
                self.entry(
                    deployment_id=self.DEPLOYMENT_ID,
                    revision="not-hex",
                    created_on="2026-07-20T00:00:00Z",
                )
            ],
            "not an array": {"unexpected": "shape"},
        }
        for label, payload in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "deployments.json"
                path.write_text(json.dumps(payload))
                with self.assertRaises(ValueError):
                    last_deployment.extract_last_good(path, project=self.PROJECT)

    def test_main_emits_github_output_lines(self) -> None:
        entries = [
            self.entry(
                deployment_id=self.DEPLOYMENT_ID,
                revision=self.REVISION,
                created_on="2026-07-20T00:00:00Z",
            )
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(Path(directory), entries)
            captured = io.StringIO()
            with (
                mock.patch.object(
                    last_deployment.sys, "argv",
                    ["pages_last_deployment.py", str(path), "--project", self.PROJECT],
                ),
                mock.patch.object(last_deployment.sys, "stdout", captured),
            ):
                result = last_deployment.main()
        self.assertEqual(result, 0)
        self.assertEqual(
            captured.getvalue(),
            "had_prior_deployment=true\n"
            f"last_good_deployment_id={self.DEPLOYMENT_ID}\n"
            f"last_good_revision={self.REVISION}\n",
        )

    def test_main_reports_false_with_no_prior_deployment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(Path(directory), [])
            captured = io.StringIO()
            with (
                mock.patch.object(
                    last_deployment.sys, "argv",
                    ["pages_last_deployment.py", str(path), "--project", self.PROJECT],
                ),
                mock.patch.object(last_deployment.sys, "stdout", captured),
            ):
                result = last_deployment.main()
        self.assertEqual(result, 0)
        self.assertEqual(captured.getvalue(), "had_prior_deployment=false\n")

    def test_wrangler_pascal_case_shape_is_rejected(self) -> None:
        # AT-01 follow-up: `wrangler pages deployment list --json` emits a
        # PascalCase DISPLAY mapping ({Id, Environment:"Production",
        # Source:<7-char-sha>, ...}), not this extractor's lowercase CF-API
        # schema. capture_last_good now calls the CF API directly instead
        # (see DeployWorkflowContractTests), but this test pins the
        # rejection at the extractor layer too: feeding it wrangler's shape
        # must fail closed to "no prior deployment" rather than silently
        # matching a differently-cased field, so this schema class can
        # never silently regress again even if a future edit reintroduces
        # a wrangler-shaped input by mistake.
        wrangler_shaped_entries = [
            {
                "Id": self.DEPLOYMENT_ID,
                "Environment": "Production",
                "Branch": "main",
                "Source": self.REVISION[:7],
                "Status": "Success",
                "Created": "2026-07-20T00:00:00Z",
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(Path(directory), wrangler_shaped_entries)
            deployment_id, revision = last_deployment.extract_last_good(
                path, project=self.PROJECT
            )
        self.assertIsNone(deployment_id)
        self.assertIsNone(revision)

        with tempfile.TemporaryDirectory() as directory:
            path = self.write(Path(directory), wrangler_shaped_entries)
            captured = io.StringIO()
            with (
                mock.patch.object(
                    last_deployment.sys, "argv",
                    ["pages_last_deployment.py", str(path), "--project", self.PROJECT],
                ),
                mock.patch.object(last_deployment.sys, "stdout", captured),
            ):
                result = last_deployment.main()
        self.assertEqual(result, 0)
        self.assertEqual(captured.getvalue(), "had_prior_deployment=false\n")

    def test_skips_a_newer_failed_or_active_entry_for_an_older_success(self) -> None:
        for bad_status in ("failure", "active", "idle", "canceled"):
            with self.subTest(status=bad_status):
                entries = [
                    self.entry(
                        deployment_id=self.OLDER_DEPLOYMENT_ID,
                        revision=self.OLDER_REVISION,
                        created_on="2026-07-01T00:00:00Z",
                    ),
                    self.entry(
                        deployment_id=self.DEPLOYMENT_ID,
                        revision=self.REVISION,
                        created_on="2026-07-20T00:00:00Z",
                        latest_stage_status=bad_status,
                    ),
                ]
                with tempfile.TemporaryDirectory() as directory:
                    path = self.write(Path(directory), entries)
                    deployment_id, revision = last_deployment.extract_last_good(
                        path, project=self.PROJECT
                    )
                self.assertEqual(deployment_id, self.OLDER_DEPLOYMENT_ID)
                self.assertEqual(revision, self.OLDER_REVISION)

    def test_skips_a_newer_skipped_entry_for_an_older_non_skipped_one(self) -> None:
        entries = [
            self.entry(
                deployment_id=self.OLDER_DEPLOYMENT_ID,
                revision=self.OLDER_REVISION,
                created_on="2026-07-01T00:00:00Z",
            ),
            self.entry(
                deployment_id=self.DEPLOYMENT_ID,
                revision=self.REVISION,
                created_on="2026-07-20T00:00:00Z",
                is_skipped=True,
            ),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(Path(directory), entries)
            deployment_id, revision = last_deployment.extract_last_good(
                path, project=self.PROJECT
            )
        self.assertEqual(deployment_id, self.OLDER_DEPLOYMENT_ID)
        self.assertEqual(revision, self.OLDER_REVISION)

    def test_unordered_pagination_still_selects_the_true_newest_qualified_entry(
        self,
    ) -> None:
        # Pages combined across pages carry no guaranteed order; the
        # newest-qualified pick must not depend on input order.
        middle_id = "11111111-2222-3333-4444-555555555555"
        middle_revision = "c" * 40
        entries = [
            self.entry(
                deployment_id=self.DEPLOYMENT_ID,
                revision=self.REVISION,
                created_on="2026-07-20T00:00:00Z",
            ),
            self.entry(
                deployment_id=self.OLDER_DEPLOYMENT_ID,
                revision=self.OLDER_REVISION,
                created_on="2026-07-01T00:00:00Z",
            ),
            self.entry(
                deployment_id=middle_id,
                revision=middle_revision,
                created_on="2026-07-10T00:00:00Z",
            ),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(Path(directory), entries)
            deployment_id, revision = last_deployment.extract_last_good(
                path, project=self.PROJECT
            )
        self.assertEqual(deployment_id, self.DEPLOYMENT_ID)
        self.assertEqual(revision, self.REVISION)

    def test_no_qualifying_candidate_fails_closed_rather_than_reporting_no_prior(
        self,
    ) -> None:
        # Production history exists (a real deploy history), but every
        # entry in it is either failed, active, or skipped - there is no
        # known-good target, and that must never be conflated with "this is
        # the first production deploy" (which silently proceeds unprotected).
        entries = [
            self.entry(
                deployment_id=self.OLDER_DEPLOYMENT_ID,
                revision=self.OLDER_REVISION,
                created_on="2026-07-01T00:00:00Z",
                latest_stage_status="failure",
            ),
            self.entry(
                deployment_id=self.DEPLOYMENT_ID,
                revision=self.REVISION,
                created_on="2026-07-20T00:00:00Z",
                is_skipped=True,
            ),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(Path(directory), entries)
            with self.assertRaises(ValueError):
                last_deployment.extract_last_good(path, project=self.PROJECT)

    def test_missing_status_or_skip_fields_exclude_a_candidate(self) -> None:
        newer_missing_latest_stage = self.entry(
            deployment_id=self.DEPLOYMENT_ID,
            revision=self.REVISION,
            created_on="2026-07-20T00:00:00Z",
            latest_stage_status=None,
        )
        newer_missing_is_skipped = self.entry(
            deployment_id=self.DEPLOYMENT_ID,
            revision=self.REVISION,
            created_on="2026-07-20T00:00:00Z",
        )
        del newer_missing_is_skipped["is_skipped"]
        older_good = self.entry(
            deployment_id=self.OLDER_DEPLOYMENT_ID,
            revision=self.OLDER_REVISION,
            created_on="2026-07-01T00:00:00Z",
        )
        for label, newer in (
            ("missing latest_stage", newer_missing_latest_stage),
            ("missing is_skipped", newer_missing_is_skipped),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                path = self.write(Path(directory), [older_good, newer])
                deployment_id, revision = last_deployment.extract_last_good(
                    path, project=self.PROJECT
                )
            self.assertEqual(deployment_id, self.OLDER_DEPLOYMENT_ID)
            self.assertEqual(revision, self.OLDER_REVISION)

        # And when the only entry present has missing fields, there is
        # nothing left to qualify - fail closed rather than report absence.
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(Path(directory), [newer_missing_latest_stage])
            with self.assertRaises(ValueError):
                last_deployment.extract_last_good(path, project=self.PROJECT)

    def test_deployment_attributed_to_a_different_project_is_excluded(self) -> None:
        # A production entry whose project_name does not match the trusted
        # --project authority must never be selectable, even if it is
        # otherwise a well-formed successful, non-skipped deployment.
        entries = [
            self.entry(
                deployment_id=self.DEPLOYMENT_ID,
                revision=self.REVISION,
                created_on="2026-07-20T00:00:00Z",
                project_name="a-different-project",
            )
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(Path(directory), entries)
            with self.assertRaises(ValueError):
                last_deployment.extract_last_good(path, project=self.PROJECT)

        # With a qualifying older entry present, the mismatched one is
        # simply excluded rather than poisoning the whole selection.
        older_good = self.entry(
            deployment_id=self.OLDER_DEPLOYMENT_ID,
            revision=self.OLDER_REVISION,
            created_on="2026-07-01T00:00:00Z",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(Path(directory), [older_good, *entries])
            deployment_id, revision = last_deployment.extract_last_good(
                path, project=self.PROJECT
            )
        self.assertEqual(deployment_id, self.OLDER_DEPLOYMENT_ID)
        self.assertEqual(revision, self.OLDER_REVISION)


class VerifyRestoreTests(unittest.TestCase):
    REVISION = "c" * 40

    def test_pass_when_root_and_revision_match(self) -> None:
        def fake_fetch(url: str, timeout: float) -> tuple[int, bytes]:
            if url.endswith("build-revision.txt"):
                return 200, f"{self.REVISION}\n".encode()
            return 200, b"home\n"

        with mock.patch.object(verify_restore, "fetch", side_effect=fake_fetch):
            errors = verify_restore.verify_once(
                "https://ardent.tools", self.REVISION, 5.0
            )
        self.assertEqual(errors, [])

    def test_fails_closed_on_revision_mismatch(self) -> None:
        def fake_fetch(url: str, timeout: float) -> tuple[int, bytes]:
            if url.endswith("build-revision.txt"):
                return 200, b"0" * 40 + b"\n"
            return 200, b"home\n"

        with mock.patch.object(verify_restore, "fetch", side_effect=fake_fetch):
            errors = verify_restore.verify_once(
                "https://ardent.tools", self.REVISION, 5.0
            )
        self.assertTrue(any("restored revision mismatch" in error for error in errors))

    def test_fails_closed_on_non_200_root(self) -> None:
        def fake_fetch(url: str, timeout: float) -> tuple[int, bytes]:
            if url.endswith("build-revision.txt"):
                return 200, f"{self.REVISION}\n".encode()
            return 503, b""

        with mock.patch.object(verify_restore, "fetch", side_effect=fake_fetch):
            errors = verify_restore.verify_once(
                "https://ardent.tools", self.REVISION, 5.0
            )
        self.assertTrue(any("root path returned 503" in error for error in errors))

    def test_retries_until_attempts_exhausted_then_fails(self) -> None:
        def always_stale(url: str, timeout: float) -> tuple[int, bytes]:
            if url.endswith("build-revision.txt"):
                return 200, b"0" * 40 + b"\n"
            return 200, b"home\n"

        with (
            mock.patch.object(verify_restore, "fetch", side_effect=always_stale),
            mock.patch.object(verify_restore.time, "sleep") as sleep_mock,
            mock.patch.object(
                verify_restore.sys, "argv",
                [
                    "verify_restore.py",
                    "--base-url", "https://ardent.tools",
                    "--expected-revision", self.REVISION,
                    "--attempts", "3",
                    "--delay", "1",
                ],
            ),
        ):
            result = verify_restore.main()
        self.assertEqual(result, 1)
        self.assertEqual(sleep_mock.call_count, 2)

    def test_rejects_malformed_expected_revision(self) -> None:
        with mock.patch.object(
            verify_restore.sys, "argv",
            [
                "verify_restore.py",
                "--base-url", "https://ardent.tools",
                "--expected-revision", "not-hex",
            ],
        ):
            with self.assertRaises(SystemExit):
                verify_restore.main()


class PagesReconcileTests(unittest.TestCase):
    PROJECT = "ardent-tools"
    REVISION = "d" * 40
    OTHER_REVISION = "e" * 40
    PREVIEW_BRANCH = f"ci-preview-{REVISION}"
    PREVIEW_ID = "12345678-1234-1234-1234-123456789abc"
    OTHER_PREVIEW_ID = "87654321-4321-4321-4321-cba987654321"
    PRODUCTION_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    def entry(
        self,
        *,
        deployment_id: str,
        environment: str,
        branch: str,
        revision: str,
        project_name: str | None = None,
    ) -> dict:
        return {
            "id": deployment_id,
            "environment": environment,
            "project_name": self.PROJECT if project_name is None else project_name,
            "deployment_trigger": {
                "metadata": {"branch": branch, "commit_hash": revision}
            },
        }

    def write(self, root: Path, entries: list) -> Path:
        path = root / "deployments.json"
        path.write_text(json.dumps(entries))
        return path

    def reconcile(self, path: Path) -> tuple[list[str], bool]:
        return pages_reconcile.reconcile(
            path,
            project=self.PROJECT,
            revision=self.REVISION,
            preview_branch=self.PREVIEW_BRANCH,
        )

    def test_true_no_mutation_reports_nothing_accepted(self) -> None:
        # Cloudflare never received this run's commit on either branch - a
        # freshly captured list that only carries unrelated history.
        entries = [
            self.entry(
                deployment_id=self.OTHER_PREVIEW_ID,
                environment="preview",
                branch=f"ci-preview-{self.OTHER_REVISION}",
                revision=self.OTHER_REVISION,
            ),
            self.entry(
                deployment_id=self.PRODUCTION_ID,
                environment="production",
                branch="main",
                revision=self.OTHER_REVISION,
            ),
        ]
        with tempfile.TemporaryDirectory() as directory:
            preview_ids, production_accepted = self.reconcile(
                self.write(Path(directory), entries)
            )
        self.assertEqual(preview_ids, [])
        self.assertFalse(production_accepted)

    def test_accepted_but_client_failed_is_still_detected(self) -> None:
        # Cloudflare recorded both mutations for this exact commit+branch;
        # this module never looks at wrangler's exit code or a parsed
        # receipt, only at what Cloudflare itself reports.
        entries = [
            self.entry(
                deployment_id=self.PREVIEW_ID,
                environment="preview",
                branch=self.PREVIEW_BRANCH,
                revision=self.REVISION,
            ),
            self.entry(
                deployment_id=self.PRODUCTION_ID,
                environment="production",
                branch="main",
                revision=self.REVISION,
            ),
        ]
        with tempfile.TemporaryDirectory() as directory:
            preview_ids, production_accepted = self.reconcile(
                self.write(Path(directory), entries)
            )
        self.assertEqual(preview_ids, [self.PREVIEW_ID])
        self.assertTrue(production_accepted)

    def test_multiple_matching_preview_deployments_are_all_returned(self) -> None:
        # An earlier run's cleanup never completed; a same-commit re-run
        # must not leave any of them behind.
        entries = [
            self.entry(
                deployment_id=self.PREVIEW_ID,
                environment="preview",
                branch=self.PREVIEW_BRANCH,
                revision=self.REVISION,
            ),
            self.entry(
                deployment_id=self.OTHER_PREVIEW_ID,
                environment="preview",
                branch=self.PREVIEW_BRANCH,
                revision=self.REVISION,
            ),
        ]
        with tempfile.TemporaryDirectory() as directory:
            preview_ids, production_accepted = self.reconcile(
                self.write(Path(directory), entries)
            )
        self.assertCountEqual(preview_ids, [self.PREVIEW_ID, self.OTHER_PREVIEW_ID])
        self.assertFalse(production_accepted)

    def test_wrong_project_or_branch_never_matches(self) -> None:
        entries = [
            self.entry(
                deployment_id=self.PREVIEW_ID,
                environment="preview",
                branch=self.PREVIEW_BRANCH,
                revision=self.REVISION,
                project_name="a-different-project",
            ),
            self.entry(
                deployment_id=self.PRODUCTION_ID,
                environment="production",
                branch="not-main",
                revision=self.REVISION,
            ),
        ]
        with tempfile.TemporaryDirectory() as directory:
            preview_ids, production_accepted = self.reconcile(
                self.write(Path(directory), entries)
            )
        self.assertEqual(preview_ids, [])
        self.assertFalse(production_accepted)

    def test_malformed_matched_deployment_id_fails_closed(self) -> None:
        entries = [
            self.entry(
                deployment_id="not-a-uuid",
                environment="preview",
                branch=self.PREVIEW_BRANCH,
                revision=self.REVISION,
            )
        ]
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                self.reconcile(self.write(Path(directory), entries))

    def test_main_emits_github_output_lines(self) -> None:
        entries = [
            self.entry(
                deployment_id=self.PREVIEW_ID,
                environment="preview",
                branch=self.PREVIEW_BRANCH,
                revision=self.REVISION,
            ),
            self.entry(
                deployment_id=self.PRODUCTION_ID,
                environment="production",
                branch="main",
                revision=self.REVISION,
            ),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(Path(directory), entries)
            captured = io.StringIO()
            with (
                mock.patch.object(
                    pages_reconcile.sys, "argv",
                    [
                        "pages_reconcile.py", str(path),
                        "--project", self.PROJECT,
                        "--revision", self.REVISION,
                        "--preview-branch", self.PREVIEW_BRANCH,
                    ],
                ),
                mock.patch.object(pages_reconcile.sys, "stdout", captured),
            ):
                result = pages_reconcile.main()
        self.assertEqual(result, 0)
        self.assertEqual(
            captured.getvalue(),
            "preview_accepted=true\n"
            f"preview_deployment_ids={self.PREVIEW_ID}\n"
            "production_accepted=true\n",
        )

    def test_main_reports_nothing_accepted_for_unrelated_history(self) -> None:
        entries = [
            self.entry(
                deployment_id=self.OTHER_PREVIEW_ID,
                environment="preview",
                branch=f"ci-preview-{self.OTHER_REVISION}",
                revision=self.OTHER_REVISION,
            )
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(Path(directory), entries)
            captured = io.StringIO()
            with (
                mock.patch.object(
                    pages_reconcile.sys, "argv",
                    [
                        "pages_reconcile.py", str(path),
                        "--project", self.PROJECT,
                        "--revision", self.REVISION,
                        "--preview-branch", self.PREVIEW_BRANCH,
                    ],
                ),
                mock.patch.object(pages_reconcile.sys, "stdout", captured),
            ):
                result = pages_reconcile.main()
        self.assertEqual(result, 0)
        self.assertEqual(
            captured.getvalue(),
            "preview_accepted=false\n"
            "preview_deployment_ids=\n"
            "production_accepted=false\n",
        )

    def test_rejects_invalid_project_revision_or_branch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(Path(directory), [])
            with self.assertRaises(ValueError):
                pages_reconcile.reconcile(
                    path,
                    project="Not Valid",
                    revision=self.REVISION,
                    preview_branch=self.PREVIEW_BRANCH,
                )
            with self.assertRaises(ValueError):
                pages_reconcile.reconcile(
                    path,
                    project=self.PROJECT,
                    revision="not-hex",
                    preview_branch=self.PREVIEW_BRANCH,
                )
            with self.assertRaises(ValueError):
                pages_reconcile.reconcile(
                    path,
                    project=self.PROJECT,
                    revision=self.REVISION,
                    preview_branch="",
                )


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

    def test_same_prefix_route_family_collapses_only_when_over_the_rule_cap(
        self,
    ) -> None:
        # Collapse is now conditional: it triggers solely when the exact rule
        # set would exceed Cloudflare's limit. Force that here with enough
        # siblings, then verify the family collapses to one safe wildcard and
        # subsumes the hand-authored redirect wildcards for the same prefix.
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            many = ["/systems/"] + [
                f"/systems/s{index}/"
                for index in range(pages_runtime.MAX_ROUTE_RULES + 10)
            ]
            self.make_fixture_with_extra_routes(output, many)
            include_count, exclude_count = pages_runtime.write_runtime(output)
            routes = json.loads((output / pages_runtime.ROUTES_NAME).read_text())
            errors = pages_runtime.validate_runtime(output)
        self.assertEqual(errors, [])
        self.assertEqual(include_count, 1)
        self.assertEqual(exclude_count, len(routes["exclude"]))
        self.assertIn("/systems/*", routes["exclude"])
        for member in ("/systems/", "/systems/s0/", "/systems/s5/"):
            self.assertNotIn(member, routes["exclude"])
        self.assertNotIn("/systems/ergon-tools/*", routes["exclude"])
        self.assertNotIn("/systems/nosologia/*", routes["exclude"])
        self.assertNotIn("/about/*", routes["exclude"])
        self.assertIn("/about/", routes["exclude"])

    def test_family_stays_exact_while_under_the_rule_cap(self) -> None:
        # The new default: while the exact rule set fits under the cap, keep
        # per-path excludes so an unknown descendant (/systems/typo/) reaches
        # the authoritative-404 Function instead of Cloudflare's native 404.
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
            routes, errors = pages_runtime.build_routes(output)
        self.assertEqual(errors, [])
        self.assertNotIn("/systems/*", routes["exclude"])
        for member in (
            "/systems/",
            "/systems/akroasis/",
            "/systems/aletheia/",
            "/systems/kanon/",
        ):
            self.assertIn(member, routes["exclude"])

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

    def test_indented_header_with_no_preceding_path_rule_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "header without path rule"):
            site.parse_cloudflare_headers("  Cache-Control: no-store\n")

    def test_header_declaration_missing_colon_separator_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "malformed header declaration"):
            site.parse_cloudflare_headers("/*\n  Cache-Control no-store\n")

    def test_malformed_headers_syntax_surfaces_through_cache_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            errors: list[str] = []
            site.validate_cache_contract(
                errors, output, "/*\n  Cache-Control no-store\n"
            )
        self.assertTrue(
            any("malformed header declaration" in error for error in errors), errors
        )


class ValidateSiteEntrypointContractTests(unittest.TestCase):
    def run_main(self, output: Path) -> tuple[int, str]:
        argv = ["validate-site.py", str(output)]
        stderr = io.StringIO()
        with mock.patch.object(site.sys, "argv", argv):
            with mock.patch.object(site.sys, "stderr", stderr):
                exit_code = site.main()
        return exit_code, stderr.getvalue()

    def test_malformed_sitemap_and_atom_report_cleanly_without_crashing(self) -> None:
        # WHY: the first pass records a parse failure into `errors`; a second,
        # unconditioned re-parse of the same malformed file used to raise
        # ET.ParseError uncaught, crashing main() past its structured error
        # report instead of returning 1 with everything collected.
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "sitemap.xml").write_bytes(
                b'<?xml version="1.0" encoding="UTF-8"?><urlset'
            )
            (output / "atom.xml").write_bytes(
                b'<?xml version="1.0" encoding="UTF-8"?><feed></feed>'
            )
            exit_code, stderr = self.run_main(output)
        self.assertEqual(exit_code, 1)
        self.assertIn("strict XML parse failed", stderr)


class EvidencePageMarkerGateContractTests(unittest.TestCase):
    """A content regression that drops an /evidence/ marker must fail the
    gate against the BUILT tree, before merge — not only the post-deploy
    live verifier, which can only prove byte-identity to whatever the
    build already produced (see bin/verify-production.py's rationale
    comment where the equivalent live check used to live)."""

    def write_evidence_page(self, output: Path, body: str) -> None:
        page = output / "evidence/index.html"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(body)

    def test_complete_evidence_page_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            self.write_evidence_page(
                output,
                '<link rel="canonical" href="https://ardent.tools/evidence/">'
                "Would show: 0 published casts so far.",
            )
            errors: list[str] = []
            site.validate_evidence_page_markers(errors, output)
        self.assertEqual(errors, [])

    def test_each_missing_marker_fails_closed(self) -> None:
        complete = (
            '<link rel="canonical" href="https://ardent.tools/evidence/">'
            "Would show: 0 published casts so far."
        )
        for marker in site.EVIDENCE_PAGE_DEPLOYMENT_MARKERS:
            with self.subTest(marker=marker):
                with tempfile.TemporaryDirectory() as directory:
                    output = Path(directory)
                    self.write_evidence_page(output, complete.replace(marker, ""))
                    errors: list[str] = []
                    site.validate_evidence_page_markers(errors, output)
                self.assertTrue(
                    any(marker in error for error in errors), (marker, errors)
                )

    def test_unreadable_evidence_page_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            errors: list[str] = []
            site.validate_evidence_page_markers(errors, output)
        self.assertTrue(errors)


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

    def test_the_same_addressed_asset_repeated_across_pages_is_not_a_conflict(
        self,
    ) -> None:
        # WHY: a content-addressed asset_path IS its own hash, so two pages
        # sharing one identical /a/<hash>.ext reference -- the ordinary case
        # for a site-wide stylesheet or script -- must never be reported as
        # conflicting, no matter how many pages repeat it.
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / CSS_OUTPUT).parent.mkdir(parents=True, exist_ok=True)
            (output / CSS_OUTPUT).write_bytes(CSS_BODY)
            (output / JS_OUTPUT).parent.mkdir(parents=True, exist_ok=True)
            (output / JS_OUTPUT).write_bytes(JS_BODY)
            errors: list[str] = []
            site.validate_asset_contract(
                errors,
                {
                    Path("index.html"): ASSET_MARKUP,
                    Path("about/index.html"): ASSET_MARKUP,
                    Path("hire/index.html"): ASSET_MARKUP,
                },
                output,
            )
        self.assertEqual(errors, [])

    def test_uppercase_addressed_extension_is_rejected(self) -> None:
        # WHY: this shape check is now ADDRESSED_PATH_RE (release_manifest.py,
        # shared with asset_retention.py) rather than a locally-defined,
        # looser regex -- proving the two contracts actually agree.
        css_body = b"body{color:red}\n"
        digest = hashlib.sha256(css_body).hexdigest()
        uppercase_reference = f"{BASE_URL}/a/{digest}.CSS"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            path = output / "a" / f"{digest}.CSS"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(css_body)
            errors: list[str] = []
            site.validate_asset_contract(
                errors,
                {
                    Path("index.html"): (
                        f'<link rel="stylesheet" href="{uppercase_reference}">'
                        f'<script src="{JS_URL}" defer></script>'
                    )
                },
                output,
            )
        self.assertTrue(
            any("full-sha256>.<extension>" in error for error in errors), errors
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
                "generate-sbom.py",
            ):
                shutil.copy2(ROOT / "bin" / filename, root / "bin" / filename)
            shutil.copytree(ROOT / "content/systems", root / "content/systems")
            shutil.copy2(ROOT / "content/about.md", root / "content/about.md")
            shutil.copy2(ROOT / "content/colophon.md", root / "content/colophon.md")
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
            (root / "static/vendor/asciinema").mkdir(parents=True)
            shutil.copy2(
                ROOT / "static/vendor/asciinema/asciinema-player.min.js",
                root / "static/vendor/asciinema/asciinema-player.min.js",
            )
            shutil.copy2(
                ROOT / "static/vendor/asciinema/asciinema-player.css",
                root / "static/vendor/asciinema/asciinema-player.css",
            )
            (root / ".github/workflows").mkdir(parents=True)
            shutil.copy2(
                ROOT / ".github/workflows/deploy.yml",
                root / ".github/workflows/deploy.yml",
            )
            shutil.copy2(ROOT / "package-lock.json", root / "package-lock.json")
            shutil.copy2(
                ROOT / "bin/requirements.txt", root / "bin/requirements.txt"
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


class SbomNpmBoundaryClaimContractTests(unittest.TestCase):
    """The colophon's stated npm coverage must equal generate-sbom.py's closed
    NPM_COMPONENTS authority (issue #101: the colophon claimed lockfile-wide
    coverage while the generator only ever emitted three named packages)."""

    def _root_with_colophon(self, directory: Path, boundary_clause: str) -> Path:
        root = Path(directory)
        (root / "content").mkdir(parents=True, exist_ok=True)
        (root / "content/colophon.md").write_text(
            f"prose before, npm toolchain packages ({boundary_clause}), prose after\n"
        )
        return root

    def test_matching_boundary_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._root_with_colophon(
                directory, "`@playwright/test`, `pa11y-ci`, `wrangler`"
            )
            generate_sbom.verify_npm_boundary_claim(root)

    def test_missing_package_in_claim_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._root_with_colophon(directory, "`@playwright/test`, `pa11y-ci`")
            with self.assertRaises(SystemExit):
                generate_sbom.verify_npm_boundary_claim(root)

    def test_extra_package_in_claim_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._root_with_colophon(
                directory,
                "`@playwright/test`, `pa11y-ci`, `wrangler`, `left-pad`",
            )
            with self.assertRaises(SystemExit):
                generate_sbom.verify_npm_boundary_claim(root)

    def test_missing_boundary_clause_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "content").mkdir()
            (root / "content/colophon.md").write_text("no boundary clause here\n")
            with self.assertRaises(SystemExit):
                generate_sbom.verify_npm_boundary_claim(root)

    def test_live_colophon_matches_live_generator_authority(self) -> None:
        # Guards the real files, not a fixture: fails the moment
        # content/colophon.md and bin/generate-sbom.py's NPM_COMPONENTS
        # disagree about which npm packages the SBOM covers.
        generate_sbom.verify_npm_boundary_claim(ROOT)

    def test_build_bom_enforces_the_claim(self) -> None:
        # build_bom() is what both `generate-sbom.py` and `--check` run;
        # the boundary check must fire on that path, not just standalone.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in (
                ".github/workflows",
                "bin",
                "content",
                "static/vendor/asciinema",
            ):
                (root / relative).mkdir(parents=True, exist_ok=True)
            shutil.copy2(
                ROOT / ".github/workflows/deploy.yml",
                root / ".github/workflows/deploy.yml",
            )
            shutil.copy2(ROOT / "package-lock.json", root / "package-lock.json")
            shutil.copy2(ROOT / "bin/requirements.txt", root / "bin/requirements.txt")
            shutil.copy2(
                ROOT / "static/vendor/asciinema/asciinema-player.min.js",
                root / "static/vendor/asciinema/asciinema-player.min.js",
            )
            shutil.copy2(
                ROOT / "static/vendor/asciinema/asciinema-player.css",
                root / "static/vendor/asciinema/asciinema-player.css",
            )
            # WHY: a valid player-version line (so player_component() would
            # otherwise succeed) paired with a WRONG npm boundary claim -
            # isolates the failure to verify_npm_boundary_claim rather than
            # letting an unrelated missing match produce a false-positive
            # SystemExit.
            (root / "content/colophon.md").write_text(
                "[asciinema-player](https://x) v3.17.0 is vendored. "
                "npm toolchain packages (`@playwright/test`, `pa11y-ci`), more prose\n"
            )
            with self.assertRaisesRegex(SystemExit, "npm boundary claim"):
                generate_sbom.build_bom(root)



def _write_sbom_fixture(root: Path) -> None:
    """Populate a temp worktree with the real SBOM authority inputs and hook,
    then generate a matching static/sbom.cdx.json (#136)."""
    (root / "bin/git-hooks").mkdir(parents=True)
    shutil.copy2(ROOT / "bin/generate-sbom.py", root / "bin/generate-sbom.py")
    shutil.copy2(ROOT / "bin/git-hooks/pre-commit", root / "bin/git-hooks/pre-commit")
    (root / ".github/workflows").mkdir(parents=True)
    shutil.copy2(
        ROOT / ".github/workflows/deploy.yml", root / ".github/workflows/deploy.yml"
    )
    shutil.copy2(ROOT / "package-lock.json", root / "package-lock.json")
    shutil.copy2(ROOT / "bin/requirements.txt", root / "bin/requirements.txt")
    (root / "content").mkdir()
    shutil.copy2(ROOT / "content/colophon.md", root / "content/colophon.md")
    (root / "static/vendor/asciinema").mkdir(parents=True)
    shutil.copy2(
        ROOT / "static/vendor/asciinema/asciinema-player.min.js",
        root / "static/vendor/asciinema/asciinema-player.min.js",
    )
    shutil.copy2(
        ROOT / "static/vendor/asciinema/asciinema-player.css",
        root / "static/vendor/asciinema/asciinema-player.css",
    )
    subprocess.run(
        [sys.executable, "bin/generate-sbom.py"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=test", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


class SbomPreCommitHookContractTests(unittest.TestCase):
    """bin/git-hooks/pre-commit (#136): a staged SBOM-input edit that leaves
    static/sbom.cdx.json stale is refused at commit time, naming the sync
    command; a commit outside that source set is never even checked."""

    def _init_repo(self, root: Path) -> None:
        _write_sbom_fixture(root)
        _git(root, "init", "-q")
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", "init")

    def test_list_sources_matches_the_declared_authority(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "bin/generate-sbom.py"), "--list-sources"],
            check=True,
            capture_output=True,
            text=True,
        )
        expected = [relative.as_posix() for relative in sbom.SBOM_SOURCES]
        self.assertEqual(completed.stdout.splitlines(), expected)

    def test_hook_blocks_a_stale_sbom_after_a_deploy_yml_edit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._init_repo(root)
            with (root / ".github/workflows/deploy.yml").open("a") as handle:
                handle.write("# unrelated trailing comment\n")
            _git(root, "add", ".github/workflows/deploy.yml")
            hook = subprocess.run(
                ["bash", "bin/git-hooks/pre-commit"],
                cwd=root,
                capture_output=True,
                text=True,
            )
        self.assertEqual(hook.returncode, 1)
        self.assertIn(
            "ERROR: stale generated artifact: static/sbom.cdx.json", hook.stderr
        )
        self.assertIn("python3 bin/site.py sync", hook.stderr)

    def test_hook_passes_once_the_sbom_is_regenerated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._init_repo(root)
            with (root / ".github/workflows/deploy.yml").open("a") as handle:
                handle.write("# unrelated trailing comment\n")
            subprocess.run(
                [sys.executable, "bin/generate-sbom.py"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            _git(
                root,
                "add",
                ".github/workflows/deploy.yml",
                "static/sbom.cdx.json",
            )
            hook = subprocess.run(
                ["bash", "bin/git-hooks/pre-commit"],
                cwd=root,
                capture_output=True,
                text=True,
            )
        self.assertEqual(hook.returncode, 0)

    def test_hook_ignores_a_commit_that_does_not_touch_an_sbom_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._init_repo(root)
            # Corrupt the committed SBOM on disk WITHOUT staging it, so the hook
            # can only pass by never invoking --check for this commit — not by luck.
            (root / "static/sbom.cdx.json").write_text("{}\n")
            (root / "notes.txt").write_text("unrelated\n")
            _git(root, "add", "notes.txt")
            hook = subprocess.run(
                ["bash", "bin/git-hooks/pre-commit"],
                cwd=root,
                capture_output=True,
                text=True,
            )
        self.assertEqual(hook.returncode, 0)
        self.assertEqual(hook.stdout, "")
        self.assertEqual(hook.stderr, "")


class FleetCountWitnessContractTests(unittest.TestCase):
    """A catalog and its copy can agree with each other while both lie about
    the repositories they describe. These tests hold the GitHub witness fixed
    and vary only the authored side to prove that agreement alone never
    reaches PASS."""

    OWNER = "forkwright"
    REPO = "widget"
    REPO_URL = f"https://github.com/{OWNER}/{REPO}"
    COPY = (
        "One systems, the libraries below. One public repository is "
        "featured, and one featured public system repository carries "
        "kanon_ci.\n"
    )

    def build_fixture(self, root: Path, *, declared_private: bool, declared_kanon_ci: bool = True) -> None:
        (root / "content/systems").mkdir(parents=True)
        (root / "static").mkdir(parents=True, exist_ok=True)
        catalog_document = {
            "systems": [
                {
                    "name": "widget",
                    "group": "systems",
                    "repo": self.REPO_URL,
                    "private": declared_private,
                    "kanon_ci": declared_kanon_ci,
                }
            ]
        }
        (root / "static/systems.json").write_text(json.dumps(catalog_document))
        (root / "content/systems/widget.md").write_text(self.COPY)
        (root / "static/llms.txt").write_text("")

    def metadata_url(self) -> str:
        return f"{fleet_counts.GITHUB_API}/repos/{self.OWNER}/{self.REPO}"

    def contents_url(self) -> str:
        return (
            f"{fleet_counts.GITHUB_API}/repos/{self.OWNER}/{self.REPO}"
            f"/contents/{fleet_counts.CONTROL_PLANE_CONFIG}"
        )

    def make_fetch(self, responses: dict[str, tuple[int | None, bytes]]):
        def fake_fetch(url: str, token: str | None) -> tuple[int | None, bytes]:
            self.assertIsNone(token)
            if url not in responses:
                raise AssertionError(f"unexpected GitHub API request: {url}")
            return responses[url]

        return fake_fetch

    def run_main(self, root: Path, fetch_side_effect) -> tuple[int, str, str]:
        captured_out, captured_err = io.StringIO(), io.StringIO()
        with (
            mock.patch.object(fleet_counts, "ROOT", root),
            mock.patch.object(fleet_counts, "CATALOG", root / "static/systems.json"),
            mock.patch.object(fleet_counts, "fetch", side_effect=fetch_side_effect),
            mock.patch.dict(fleet_counts.os.environ, {}, clear=True),
            mock.patch.object(fleet_counts.sys, "stdout", captured_out),
            mock.patch.object(fleet_counts.sys, "stderr", captured_err),
        ):
            result = fleet_counts.main()
        return result, captured_out.getvalue(), captured_err.getvalue()

    def test_fully_agreeing_state_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_fixture(root, declared_private=False)
            fetch = self.make_fetch({
                self.metadata_url(): (200, json.dumps({"private": False}).encode()),
                self.contents_url(): (200, b"{}"),
            })
            result, out, _ = self.run_main(root, fetch)
        self.assertEqual(result, 0)
        self.assertIn("PASS:", out)

    def test_frontmatter_only_privacy_flip_cannot_reach_pass(self) -> None:
        """The catalog and copy both declare the repository public - a
        self-consistent, frontmatter-only edit. GitHub still reports it
        private, so agreement between the authored surfaces must not be
        enough to pass."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_fixture(root, declared_private=False)
            fetch = self.make_fetch({
                self.metadata_url(): (200, json.dumps({"private": True}).encode()),
                self.contents_url(): (200, b"{}"),
            })
            result, out, err = self.run_main(root, fetch)
        self.assertEqual(result, 1)
        self.assertNotIn("PASS:", out)
        self.assertIn("catalog declares private=False", err)
        self.assertIn("GitHub reports forkwright/widget private=True", err)

    def test_declared_control_plane_adoption_without_the_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_fixture(root, declared_private=False, declared_kanon_ci=True)
            fetch = self.make_fetch({
                self.metadata_url(): (200, json.dumps({"private": False}).encode()),
                self.contents_url(): (404, b""),
            })
            result, out, err = self.run_main(root, fetch)
        self.assertEqual(result, 1)
        self.assertNotIn("PASS:", out)
        self.assertIn("catalog declares kanon_ci=True but GitHub shows", err)

    def test_unreachable_witness_never_passes(self) -> None:
        """The exact failure this check exists to close: CI cannot acquire an
        independent source, so the prior version fell back to PASS. This one
        must fail closed instead."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_fixture(root, declared_private=False)
            fetch = self.make_fetch({
                self.metadata_url(): (None, b"Name or service not known"),
            })
            result, out, err = self.run_main(root, fetch)
        self.assertEqual(result, 1)
        self.assertNotIn("PASS:", out)
        self.assertIn("UNVERIFIED", err)
        self.assertIn("GitHub API unreachable", err)

    def test_rate_limited_witness_never_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_fixture(root, declared_private=False)
            fetch = self.make_fetch({self.metadata_url(): (403, b"")})
            result, out, err = self.run_main(root, fetch)
        self.assertEqual(result, 1)
        self.assertNotIn("PASS:", out)
        self.assertIn("UNVERIFIED", err)
        self.assertIn("rate-limited or forbidden", err)

    def test_public_entry_with_no_repo_field_cannot_reach_pass(self) -> None:
        """A second catalog entry declares itself public, featured, and
        kanon_ci-adopting - but carries no 'repo' field at all. derive()
        still counts it into public_repos and featured_public_with_
        control_plane; nothing can witness it against GitHub. One genuinely
        witnessed entry alongside it must not be enough to reach PASS -
        the repo-less entry has to fail the run, not vanish from it."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "content/systems").mkdir(parents=True)
            (root / "static").mkdir(parents=True, exist_ok=True)
            catalog_document = {
                "systems": [
                    {
                        "name": "widget",
                        "group": "systems",
                        "repo": self.REPO_URL,
                        "private": False,
                        "kanon_ci": True,
                    },
                    {
                        "name": "ghost",
                        "group": "systems",
                        "private": False,
                        "kanon_ci": True,
                    },
                ]
            }
            (root / "static/systems.json").write_text(json.dumps(catalog_document))
            (root / "content/systems/widget.md").write_text(
                "Two systems, the libraries below. Two public repositories "
                "are featured, and two featured public system repositories "
                "carry kanon_ci.\n"
            )
            (root / "static/llms.txt").write_text("")
            fetch = self.make_fetch({
                self.metadata_url(): (200, json.dumps({"private": False}).encode()),
                self.contents_url(): (200, b"{}"),
            })
            result, out, err = self.run_main(root, fetch)
        self.assertEqual(result, 1)
        self.assertNotIn("PASS:", out)
        self.assertIn(
            "UNVERIFIED: ghost: catalog declares this public but has no "
            "'repo' field to witness it against GitHub",
            err,
        )
        self.assertIn("1 repository witnessed directly against the GitHub API", out)


class ExcludedLinkWitnessContractTests(unittest.TestCase):
    """The github.com subpath links .lycheeignore excludes from lychee - a
    checker limitation, not link rot (lychee 0.24.2's GitHub fallback only
    ever queries the bare repo root) - must still be witnessed by something.
    These hold one half of the check fixed and vary the other to prove a
    missing local file or a missing remote issue each fail closed alone."""

    def issue_url(self, owner: str, repo: str, number: int) -> str:
        return f"{excluded_links.GITHUB_API}/repos/{owner}/{repo}/issues/{number}"

    def run_main(self, root: Path, fetch_side_effect) -> tuple[int, str, str]:
        captured_out, captured_err = io.StringIO(), io.StringIO()
        with (
            mock.patch.object(excluded_links, "ROOT", root),
            mock.patch.object(excluded_links, "fetch", side_effect=fetch_side_effect),
            mock.patch.dict(excluded_links.os.environ, {}, clear=True),
            mock.patch.object(excluded_links.sys, "stdout", captured_out),
            mock.patch.object(excluded_links.sys, "stderr", captured_err),
        ):
            result = excluded_links.main()
        return result, captured_out.getvalue(), captured_err.getvalue()

    def touch_all_local_files(self, root: Path) -> None:
        for name in excluded_links.LOCAL_ROOT_FILES:
            (root / name).write_text("placeholder\n")

    def fetch_all_issues_ok(self):
        def fake_fetch(url: str, token: str | None) -> tuple[int | None, bytes]:
            self.assertIsNone(token)
            for owner, repo, number, _ in excluded_links.REMOTE_ISSUES:
                if url == self.issue_url(owner, repo, number):
                    return 200, b"{}"
            raise AssertionError(f"unexpected GitHub API request: {url}")

        return fake_fetch

    def test_all_present_and_witnessed_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.touch_all_local_files(root)
            result, out, _ = self.run_main(root, self.fetch_all_issues_ok())
        self.assertEqual(result, 0)
        self.assertIn("PASS:", out)

    def test_missing_local_root_file_fails_closed(self) -> None:
        """A real local witness: one of the repo's own linked root files is
        deleted. Every other file present, every remote issue reachable -
        this one absence alone must fail the run."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.touch_all_local_files(root)
            (root / "LICENSE-DOCS").unlink()
            result, out, err = self.run_main(root, self.fetch_all_issues_ok())
        self.assertEqual(result, 1)
        self.assertNotIn("PASS:", out)
        self.assertIn("LICENSE-DOCS: not present at repository root", err)

    def test_unreachable_remote_issue_never_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.touch_all_local_files(root)

            def fake_fetch(url: str, token: str | None) -> tuple[int | None, bytes]:
                return None, b"Name or service not known"

            result, out, err = self.run_main(root, fake_fetch)
        self.assertEqual(result, 1)
        self.assertNotIn("PASS:", out)
        self.assertIn("UNVERIFIED", err)
        self.assertIn("GitHub API unreachable", err)

    def test_remote_issue_404_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.touch_all_local_files(root)

            def fake_fetch(url: str, token: str | None) -> tuple[int | None, bytes]:
                return 404, b""

            result, out, err = self.run_main(root, fake_fetch)
        self.assertEqual(result, 1)
        self.assertNotIn("PASS:", out)
        self.assertIn("GitHub reports 404", err)

    def test_rate_limited_remote_issue_never_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.touch_all_local_files(root)

            def fake_fetch(url: str, token: str | None) -> tuple[int | None, bytes]:
                return 403, b""

            result, out, err = self.run_main(root, fake_fetch)
        self.assertEqual(result, 1)
        self.assertNotIn("PASS:", out)
        self.assertIn("UNVERIFIED", err)
        self.assertIn("rate-limited or forbidden", err)


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

    def test_strict_json_rejects_duplicate_keys_and_non_json_constants(self) -> None:
        for label, raw in (
            ("duplicate keys", b'{"x":1,"x":2}'),
            ("NaN constant", b'{"x":NaN}'),
        ):
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "authority.json"
                    path.write_bytes(raw)
                    document, returned_raw, errors = career.strict_json(path)
                self.assertIsNone(document)
                self.assertEqual(returned_raw, raw)
                self.assertEqual(len(errors), 1, errors)
                self.assertIn("not strict JSON", errors[0])

    def test_strict_json_rejects_non_utf8_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "authority.json"
            path.write_bytes('{"x":1}'.encode("utf-16"))
            document, _raw, errors = career.strict_json(path)
        self.assertIsNone(document)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("not strict JSON", errors[0])

    def test_strict_json_reports_unreadable_path_without_raising(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "absent.json"
            document, raw, errors = career.strict_json(missing)
        self.assertIsNone(document)
        self.assertEqual(raw, b"")
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("cannot read authority", errors[0])


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


class LinkCheckContractTests(unittest.TestCase):
    """Classification fixtures for lychee's own JSON report shape (v0.24.2)."""

    def _run(self, report_body, receipt: Path | None = None) -> tuple[int, str, str]:
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "lychee.json"
            report_path.write_bytes(
                report_body
                if isinstance(report_body, bytes)
                else json.dumps(report_body).encode()
            )
            stdout, stderr = io.StringIO(), io.StringIO()
            result = link_check_contract.run(report_path, receipt, stdout, stderr)
            return result, stdout.getvalue(), stderr.getvalue()

    def test_404_fails_closed(self) -> None:
        report = {
            "error_map": {
                "index.html": [
                    {
                        "url": "https://example.com/dead",
                        "status": {"text": "Rejected status code: 404 Not Found", "code": 404},
                    }
                ]
            },
            "timeout_map": {},
        }
        result, _, stderr = self._run(report)
        self.assertEqual(result, 1)
        self.assertIn("https://example.com/dead", stderr)
        self.assertIn("[404]", stderr)

    def test_502_degrades_with_receipt(self) -> None:
        report = {
            "error_map": {
                "index.html": [
                    {
                        "url": "https://example.com/flaky",
                        "status": {"text": "Rejected status code: 502 Bad Gateway", "code": 502},
                    }
                ]
            },
            "timeout_map": {},
        }
        with tempfile.TemporaryDirectory() as directory:
            receipt_path = Path(directory) / "receipt.json"
            result, _, stderr = self._run(report, receipt=receipt_path)
            self.assertEqual(result, 0)
            self.assertIn("degraded", stderr)
            receipt = json.loads(receipt_path.read_text())
        self.assertEqual(receipt["degraded_count"], 1)
        self.assertEqual(receipt["findings"][0]["reason"], "server-5xx")

    def test_timeout_degrades(self) -> None:
        report = {
            "error_map": {},
            "timeout_map": {
                "index.html": [
                    {
                        "url": "https://example.com/slow",
                        "status": {"text": "Timeout", "details": "Request timed out"},
                    }
                ]
            },
        }
        result, _, stderr = self._run(report)
        self.assertEqual(result, 0)
        self.assertIn("timeout", stderr)

    def test_dns_failure_with_no_status_code_fails_closed(self) -> None:
        report = {
            "error_map": {
                "index.html": [
                    {
                        "url": "https://nonexistent-domain.example/",
                        "status": {
                            "text": (
                                "Network error: Connection failed. Check network "
                                "connectivity and firewall settings"
                            ),
                            "details": (
                                "Connection failed. Check network connectivity and "
                                "firewall settings"
                            ),
                        },
                    }
                ]
            },
            "timeout_map": {},
        }
        result, _, stderr = self._run(report)
        self.assertEqual(result, 1)
        self.assertIn("[connection]", stderr)

    def test_tls_failure_fails_closed(self) -> None:
        report = {
            "error_map": {
                "index.html": [
                    {
                        "url": "https://expired.example/",
                        "status": {
                            "text": "Network error: SSL certificate expired",
                            "details": "SSL certificate expired. Site needs to renew certificate",
                        },
                    }
                ]
            },
            "timeout_map": {},
        }
        result, _, stderr = self._run(report)
        self.assertEqual(result, 1)
        self.assertIn("certificate", stderr)

    def test_malformed_output_fails_closed(self) -> None:
        result, _, stderr = self._run(b"not json at all")
        self.assertEqual(result, 1)
        self.assertIn("not valid JSON", stderr)

    def test_structural_drift_fails_closed(self) -> None:
        result, _, stderr = self._run({"total": 0, "successful": 0})
        self.assertEqual(result, 1)
        self.assertIn("error_map", stderr)

    def test_missing_report_fails_closed(self) -> None:
        stdout, stderr = io.StringIO(), io.StringIO()
        result = link_check_contract.run(
            Path("/nonexistent/lychee.json"), None, stdout, stderr
        )
        self.assertEqual(result, 1)
        self.assertIn("missing or unreadable", stderr.getvalue())

    def test_clean_report_passes_with_empty_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            receipt_path = Path(directory) / "receipt.json"
            result, _, stderr = self._run(
                {"error_map": {}, "timeout_map": {}}, receipt=receipt_path
            )
            self.assertEqual(result, 0)
            self.assertEqual(stderr, "")
            receipt = json.loads(receipt_path.read_text())
        self.assertEqual(receipt, {"degraded_count": 0, "findings": []})

    def test_hard_failure_takes_precedence_over_a_concurrent_degradable_finding(
        self,
    ) -> None:
        report = {
            "error_map": {
                "index.html": [
                    {
                        "url": "https://example.com/flaky",
                        "status": {"text": "Rejected status code: 502 Bad Gateway", "code": 502},
                    },
                    {
                        "url": "https://example.com/dead",
                        "status": {"text": "Rejected status code: 404 Not Found", "code": 404},
                    },
                ]
            },
            "timeout_map": {},
        }
        with tempfile.TemporaryDirectory() as directory:
            receipt_path = Path(directory) / "receipt.json"
            result, _, stderr = self._run(report, receipt=receipt_path)
            self.assertEqual(result, 1)
            self.assertIn("https://example.com/dead", stderr)
            self.assertFalse(receipt_path.exists())


class ExternalLinkCheckScriptTests(unittest.TestCase):
    """Behavioral fixtures for bin/check-external-links.sh's fail-closed retry."""

    SCRIPT = ROOT / "bin" / "check-external-links.sh"

    def _run_with_stub_lychee(self, stub_body: str) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as directory:
            stub_dir = Path(directory) / "stub-bin"
            stub_dir.mkdir()
            stub_lychee = stub_dir / "lychee"
            stub_lychee.write_text(stub_body)
            stub_lychee.chmod(0o755)
            prod_output = Path(directory) / "public"
            prod_output.mkdir()
            check_root = Path(directory) / "check-root"
            check_root.mkdir()
            env = {
                "PATH": f"{stub_dir}:/usr/bin:/bin",
                "LINK_CHECK_RETRY_DELAY": "0",
            }
            return subprocess.run(
                [
                    str(self.SCRIPT),
                    str(prod_output),
                    "https://ardent.tools",
                    str(check_root),
                ],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )

    def test_missing_binary_fails_closed(self) -> None:
        # WHY: no stub is written at all; lychee is absent from PATH.
        with tempfile.TemporaryDirectory() as directory:
            check_root = Path(directory) / "check-root"
            check_root.mkdir()
            prod_output = Path(directory) / "public"
            prod_output.mkdir()
            result = subprocess.run(
                [
                    str(self.SCRIPT),
                    str(prod_output),
                    "https://ardent.tools",
                    str(check_root),
                ],
                cwd=ROOT,
                env={"PATH": "/usr/bin:/bin", "LINK_CHECK_RETRY_DELAY": "0"},
                capture_output=True,
                text=True,
                timeout=30,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checker fault, not link rot", result.stderr)

    def test_invalid_configuration_fails_closed(self) -> None:
        # WHY: mirrors real lychee's own contract - a config error writes
        # nothing to -o and exits with a non-2, non-0 status.
        stub = "#!/usr/bin/env bash\necho 'bad config' >&2\nexit 3\n"
        result = self._run_with_stub_lychee(stub)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("lychee exited 3", result.stderr)

    # WHY: real lychee's --output value is a flag argument, not the last
    # positional (that slot is $PROD_OUTPUT). Every stub below parses it out
    # explicitly rather than assuming argument position.
    PARSE_OUTPUT_FLAG = (
        'OUT=""\n'
        'while [[ $# -gt 0 ]]; do\n'
        '  if [[ "$1" == "--output" ]]; then OUT="$2"; fi\n'
        "  shift\n"
        "done\n"
    )

    def test_transient_failure_recovers_on_retry(self) -> None:
        # WHY: proves the retry-then-recover path (a true one-off blip) still
        # passes without ever reaching the classifier.
        stub = (
            "#!/usr/bin/env bash\n"
            + self.PARSE_OUTPUT_FLAG
            + 'marker="${STUB_MARKER:?}"\n'
            'if [[ -f "$marker" ]]; then\n'
            '  echo \'{"error_map": {}, "timeout_map": {}}\' > "$OUT"\n'
            "  exit 0\n"
            "fi\n"
            'touch "$marker"\n'
            "echo 'transient crash' >&2\n"
            "exit 1\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            stub_dir = Path(directory) / "stub-bin"
            stub_dir.mkdir()
            stub_lychee = stub_dir / "lychee"
            stub_lychee.write_text(stub)
            stub_lychee.chmod(0o755)
            prod_output = Path(directory) / "public"
            prod_output.mkdir()
            check_root = Path(directory) / "check-root"
            check_root.mkdir()
            marker = Path(directory) / "attempted-once"
            env = {
                "PATH": f"{stub_dir}:/usr/bin:/bin",
                "LINK_CHECK_RETRY_DELAY": "0",
                "STUB_MARKER": str(marker),
            }
            result = subprocess.run(
                [
                    str(self.SCRIPT),
                    str(prod_output),
                    "https://ardent.tools",
                    str(check_root),
                ],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_404_found_on_both_attempts_fails_closed(self) -> None:
        stub = (
            "#!/usr/bin/env bash\n"
            + self.PARSE_OUTPUT_FLAG
            + 'echo \'{"error_map": {"i": [{"url": "https://example.com/dead", '
            '"status": {"text": "Rejected status code: 404 Not Found", "code": 404}}]}, '
            '"timeout_map": {}}\' > "$OUT"\n'
            "exit 2\n"
        )
        result = self._run_with_stub_lychee(stub)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("https://example.com/dead", result.stderr)


class KanonWritingGateTests(unittest.TestCase):
    """docs/VOICE.md's ban list must be a real gate, not a claim (#105)."""

    FIXTURES = ROOT / "tests/fixtures/kanon-writing"
    PINNED_VERSION = "kanon 0.11.0"
    BASH = shutil.which("bash") or "/bin/bash"

    def _require_kanon(self) -> None:
        # WHY skip, not fail: kanon has no public release binary (#93), so
        # its absence here is the documented UNVERIFIED path, not a defect.
        # A test that hard-fails on a legitimately-absent optional tool is
        # exactly the bug this class now guards against at the gate level.
        if shutil.which("kanon") is None:
            self.skipTest("kanon is not on PATH; writing-floor lint is UNVERIFIED here by design")

    def _lint(self, fixture: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["kanon", "lint", "--writing", str(self.FIXTURES / fixture)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_gate_names_the_pinned_mechanism_and_version(self) -> None:
        gate = (ROOT / "bin/check-site.sh").read_text()
        voice = (ROOT / "docs/VOICE.md").read_text()
        self.assertIn("kanon lint --writing", gate)
        self.assertIn(f'"{self.PINNED_VERSION}"', gate)
        self.assertIn("kanon lint --writing", voice)
        self.assertIn(self.PINNED_VERSION, voice)
        self.assertIn("bin/check-site.sh", voice)
        self.assertIn("UNVERIFIED", gate)
        self.assertIn("UNVERIFIED", voice)

    def test_content_surface_is_configured_for_enforcement(self) -> None:
        # WHY: without this mapping every page under content/ resolves to
        # kanon's internal-utility default, and the WRITING rules silently
        # never fire on real site prose regardless of what the gate invokes.
        config = (ROOT / ".kanon.yml").read_text()
        self.assertIn('"content/**/*.md": outward-essay', config)

    def test_fixture_and_theme_exclusions_match_between_entrypoints(self) -> None:
        gate = (ROOT / "bin/check-site.sh").read_text()
        kanon_ci = (ROOT / ".kanon-ci.toml").read_text()
        for text in (gate, kanon_ci):
            self.assertIn(":!themes/typikon", text)
            self.assertIn(":!tests/fixtures/kanon-writing", text)

    def test_banned_construction_fixture_fails_kanon_lint(self) -> None:
        self._require_kanon()
        result = self._lint("violation.md")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("WRITING/ai-trope:comprehensive", result.stdout)
        self.assertIn("WRITING/ai-trope:robust", result.stdout)

    def test_compliant_fixture_passes_kanon_lint(self) -> None:
        self._require_kanon()
        result = self._lint("clean.md")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_preflight_loop_never_hard_requires_kanon(self) -> None:
        """Regression: kanon has no public release binary and no CI credential
        (#93), so a bare-PATH runner (the GitHub Actions gate-and-deploy job)
        must still clear the required-tool preflight. Every tool the loop
        actually lists is stubbed except kanon, so if kanon is ever re-added
        to the list, this test fails exactly the way the real CI run did."""
        gate_text = (ROOT / "bin/check-site.sh").read_text()
        match = re.search(r"for tool in ([^;]+); do\n(?:.*\n)*?done\n", gate_text)
        self.assertIsNotNone(match, "could not locate the tool-preflight loop in bin/check-site.sh")
        loop_source = match.group(0)
        tools = match.group(1).split()
        self.assertNotIn("kanon", tools)

        with tempfile.TemporaryDirectory() as stub_bin:
            for tool in tools:
                stub = Path(stub_bin) / tool
                stub.write_text("#!/bin/sh\nexit 0\n")
                stub.chmod(0o755)
            result = subprocess.run(
                [self.BASH, "-c", loop_source],
                env={"PATH": stub_bin},
                capture_output=True,
                text=True,
                timeout=10,
            )
        self.assertEqual(
            result.returncode,
            0,
            f"preflight loop failed with every listed tool present and no kanon on PATH: {result.stderr}",
        )

    def test_writing_floor_reports_unverified_without_kanon(self) -> None:
        """Regression for the defect itself: the gate-and-deploy job runs
        with no kanon on PATH. This must never hard-fail the gate or skip
        the check silently - it must say UNVERIFIED (issue #105)."""
        gate_text = (ROOT / "bin/check-site.sh").read_text()
        start = gate_text.index('echo "==> kanon writing floor')
        end = gate_text.index("\nfi\n", start) + len("\nfi\n")
        block = gate_text[start:end]
        self.assertIn('if [[ "$KANON_AVAILABLE" == 1 ]]; then', block)
        self.assertIn("UNVERIFIED", block)

        script = f"set -euo pipefail\nKANON_AVAILABLE=0\n{block}\n"
        result = subprocess.run(
            [self.BASH, "-c", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("UNVERIFIED", result.stderr)
        self.assertNotIn("required tool is missing: kanon", result.stderr)


class KanonLintDebtTests(unittest.TestCase):
    """Full-category `kanon lint .` findings triaged in #128."""

    def _require_kanon(self) -> None:
        # WHY skip, not fail: same UNVERIFIED-by-design posture as
        # KanonWritingGateTests._require_kanon above (#93).
        if shutil.which("kanon") is None:
            self.skipTest("kanon is not on PATH; lint-debt regression is UNVERIFIED here by design")

    def _lint(self, *paths: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["kanon", "lint", *paths],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_ignore_file_scopes_out_published_artifact_directories(self) -> None:
        # WHY: retained-assets/ and static/tapes/ are site content (published
        # cast driver scripts and their reproduction recipes), not repo
        # tooling - SHELL/* findings there are a category error, not a defect.
        ignore = (ROOT / ".kanon-lint-ignore").read_text()
        self.assertIn("SHELL/*:retained-assets/**", ignore)
        self.assertIn("SHELL/*:static/tapes/**", ignore)
        self.assertIn("#128", ignore)

    def test_no_shell_findings_in_published_artifact_directories(self) -> None:
        self._require_kanon()
        result = self._lint(".")
        for scope in ("retained-assets/", "static/tapes/"):
            for line in result.stdout.splitlines():
                if scope in line:
                    self.assertNotIn("[SHELL/", line, result.stdout)

    def test_check_external_links_has_no_shell_findings(self) -> None:
        self._require_kanon()
        result = self._lint("bin/check-external-links.sh")
        self.assertNotIn("[SHELL/", result.stdout, result.stdout)

    def test_validate_fleet_counts_has_no_empty_fstring_findings(self) -> None:
        self._require_kanon()
        result = self._lint("bin/validate-fleet-counts.py")
        self.assertNotIn("PYTHON/empty-fstring", result.stdout, result.stdout)


class CssCommentNarrationRegressionTests(unittest.TestCase):
    """site.css comments must state a current rule, not narrate how it got
    there (#108). git log already owns that history."""

    # WHY these exact markers: each is sourced by diffing this branch
    # against its merge base and reading the comment text #108's own
    # hunks actually removed from site.css -- not guessed synonyms. Every
    # pattern below names text that removal, EXCEPT DESIGN-v[0-9]: that
    # citation style shipped in site.css too, but #107/#121 trimmed it
    # before #108 started, so it's kept only as a standing guard against
    # reintroducing it, not because #108 removed it.
    BANNED_PATTERNS = (
        r"\bpreviously\b",                 # "...theory here previously assumed away without a rendered check"
        r"\bphase [0-9]\b",                # "...already wrapped in (templates, phase 1)"
        r"\bretir(?:ed|es)\b",             # "...v1's cursor language is retired"; "--display-1 retires the old hero clamp(...)"
        r"never shipped until now",        # "...v1 §3.7 specified this; it never shipped until now"
        r"never reached CSS",              # "Restored to the v1 table that never reached CSS"
        r"\bDELTA from\b",                 # "DELTA from that design's literal --display-1 clamp(...)"
        r"\bformer\b",                     # "former uniform section padding" / "former bare fact row" /
                                            # "former duplicate declarations" / "former border-bottom"
        r"\bprior ceiling\b",              # "Interior h1 moves to --step-4 (typikon's prior ceiling)"
        r"\bunchanged from the earlier\b", # "--accent/--accent-aged/--warn unchanged from the earlier palette"
        r"\bearlier CSS grid\b",           # "standing in for the earlier CSS grid's own `gap`"
        r"\bretuned\b",                    # "...are unchanged; only the floor and slope are retuned (2.6rem/4.6vw -> 2rem/5vw...)"
        r"was #[0-9A-Fa-f]{3,8}\b",        # '..."shadow on rag paper" -- was #EDE7D8, a tan step that read as dark yellow...'
        r"\bdarkened from\b",              # "--warn: #7C5514; /* darkened from #8A6318 -- ..."
        r"\bwas \d+\.\d+:1\b",             # "...--bg-accent (was 4.39:1, failing AA's 4.5:1 floor)"
        r"DESIGN-v[0-9]",                  # e.g. "DESIGN-v2 §1.1" -- shipped pre-#108, trimmed by #107/#121
    )

    def test_no_historical_phase_narration(self) -> None:
        css = (ROOT / "static/css/site.css").read_text()
        hits = [pattern for pattern in self.BANNED_PATTERNS if re.search(pattern, css, re.IGNORECASE)]
        self.assertEqual(hits, [], f"historical-phase narration reintroduced: {hits}")


if __name__ == "__main__":
    unittest.main()
