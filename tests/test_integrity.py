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
catalog = load_script("ardent_generate_catalog", "generate-systems-json.py")
career = load_script("ardent_career_claims", "validate-career-claims.py")
site_entrypoint = load_script("ardent_site_entrypoint", "site.py")
resume_fonts = load_script("ardent_resume_fonts", "validate-resume-fonts.py")
release = load_script("ardent_release_manifest", "release_manifest.py")

BASE_URL = "https://ardent.tools"
EXPECTED_REVISION = "2" * 40
ASSET_EPOCH = "2"
CSS_BODY = b"body { color: #231f20; }\n"
JS_BODY = b"document.documentElement.dataset.ready = 'true';\n"
ERROR_JS_BODY = b"document.documentElement.dataset.errorPage = 'true';\n"
CSS_HASH = hashlib.sha256(CSS_BODY).hexdigest()[:20]
JS_HASH = hashlib.sha256(JS_BODY).hexdigest()[:20]
ERROR_JS_HASH = hashlib.sha256(ERROR_JS_BODY).hexdigest()[:20]
CSS_URL = f"{BASE_URL}/css/site.css?h={CSS_HASH}&v={ASSET_EPOCH}"
JS_URL = f"{BASE_URL}/js/site.js?h={JS_HASH}&v={ASSET_EPOCH}"
ERROR_JS_URL = f"{BASE_URL}/js/error.js?h={ERROR_JS_HASH}&v={ASSET_EPOCH}"
ASSET_MARKUP = (
    f'<link rel="stylesheet" href="{CSS_URL}"><script src="{JS_URL}" defer></script>'
)
GOOD_CACHE = "no-store, no-transform"
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
    css_cache: str = GOOD_CACHE,
    js_body: bytes = JS_BODY,
    js_cache: str = GOOD_CACHE,
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
        "Evidence register 0 published casts."
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
            "css/site.css": CSS_BODY,
            "js/site.js": JS_BODY,
            "js/error.js": ERROR_JS_BODY,
            "llms.txt": b"release fixture\n",
            "robots.txt": b"User-agent: *\n",
            "runtime-boundary.json": b"{}\n",
            "site.webmanifest": b"{}\n",
            "sitemap.xml": sitemap_body,
            "speculation-rules.json": b"{}\n",
            "systems.json": b"[]\n",
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
            output, EXPECTED_REVISION, ASSET_EPOCH, contract
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
            status = 200
            cache = GOOD_CACHE
            if item["output_path"] == "build-revision.txt":
                body = f"{revision}\n".encode()
                cache = revision_cache
            elif item["output_path"] == "css/site.css":
                body = css_body
                cache = css_cache
            elif item["output_path"] == "js/site.js":
                body = js_body
                cache = js_cache
                status = js_status
            elif item["output_path"] == "js/error.js":
                body = error_js_body
            if resource_overrides and item["output_path"] in resource_overrides:
                status, cache, body = resource_overrides[item["output_path"]]
            url = f"{BASE_URL}{item['request_url']}"
            response_headers = with_cache(cache)
            if item["output_path"] == "speculation-rules.json":
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
                "Evidence register 0 published casts."
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
                ASSET_EPOCH,
                manifest,
                manifest_bytes,
                contract["manifest_name"],
                redirect_rules,
                html_authority,
                direct_contract,
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
        self.assertTrue(all("/js/site.js?h=" in error for error in errors), errors)

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
        self.assertIn("returned 404, expected direct 200", errors[0])
        self.assertIn("/js/site.js", errors[0])

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
            errors, f"{BASE_URL}/", f"{BASE_URL}/", body, ASSET_EPOCH
        )
        self.assertEqual(assets, [])
        self.assertEqual(len(errors), 3, errors)
        self.assertTrue(
            any("exactly one h and one v" in error for error in errors), errors
        )
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
        self.assertTrue(
            any("no authored JavaScript" in error for error in errors), errors
        )

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

    def test_custom_404_malformed_asset_epoch_fails(self) -> None:
        malformed = (
            "404: no such path Return home "
            f'<link rel="stylesheet" href="{CSS_URL}">'
            f'<script src="/js/site.js?h={JS_HASH}&v=1"></script>'
        ).encode()
        errors = run_production_fixture(self, custom_404_body=malformed)
        self.assertTrue(any("expected '2'" in error for error in errors), errors)

    def test_custom_404_only_asset_stale_bytes_fail_digest(self) -> None:
        errors = run_production_fixture(
            self, error_js_body=b"stale custom 404 script\n"
        )
        self.assertTrue(
            any(
                "release resource digest mismatch" in error and "/js/error.js" in error
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


class ReleaseManifestContractTests(unittest.TestCase):
    def make_fixture(self, output: Path) -> tuple[dict, dict, bytes]:
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
            "sitemap.xml": b"<urlset/>\n",
            "systems.json": b"{}\n",
            "files/report.pdf": b"pdf bytes\n",
        }
        for relative, body in bodies.items():
            path = output / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        manifest = release.build_manifest(
            output, EXPECTED_REVISION, ASSET_EPOCH, contract
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
                expected_epoch=ASSET_EPOCH,
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
                expected_epoch=ASSET_EPOCH,
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
                expected_epoch=ASSET_EPOCH,
                contract=contract,
            )
        self.assertTrue(any("resource_count" in error for error in errors), errors)
        self.assertTrue(
            any("duplicate request_url" in error for error in errors), errors
        )

    def test_manifest_stale_digest_and_missing_artifact_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            contract, _manifest, raw = self.make_fixture(output)
            (output / "files/report.pdf").write_bytes(b"changed\n")
            _, stale_errors = release.validate_manifest(
                raw,
                output=output,
                expected_revision=EXPECTED_REVISION,
                expected_epoch=ASSET_EPOCH,
                contract=contract,
            )
            (output / "files/report.pdf").unlink()
            _, missing_errors = release.validate_manifest(
                raw,
                output=output,
                expected_revision=EXPECTED_REVISION,
                expected_epoch=ASSET_EPOCH,
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
            (output / "site.webmanifest").write_text(
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
            (output / "site.webmanifest").write_text(
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
                if item["output_path"] == "files/report.pdf"
            )
            exact = f"{BASE_URL}{report['request_url']}"
            cases = {
                "unversioned absolute": f"{BASE_URL}/files/report.pdf",
                "unversioned relative": "files/report.pdf",
                "explicit default port": exact.replace(
                    "https://ardent.tools/", "https://ardent.tools:443/"
                ),
                "percent-encoded alias": exact.replace("report.pdf", "%72eport.pdf"),
                "dot-segment alias": exact.replace(
                    "/files/report.pdf", "/files/../files/report.pdf"
                ),
                "root-relative backslash alias": report["request_url"].replace(
                    "/files/", "/files\\"
                ),
                "absolute backslash alias": exact.replace("/files/", "/files\\"),
                "encoded backslash alias": exact.replace("/files/", "/files%5c"),
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
                "raw-script HTML entity": exact.replace("&v=", "&amp;v="),
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
            contract, _manifest, _raw = self.make_fixture(output)
            (output / "css").mkdir()
            (output / "css/font.woff2").write_bytes(b"font bytes\n")
            manifest = release.build_manifest(
                output, EXPECTED_REVISION, ASSET_EPOCH, contract
            )
            (output / "css/app.css").write_text(
                "/* a maintainer's note */\n"
                '.sample { background: url("font.woff2"); }\n'
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
            contract, _manifest, _raw = self.make_fixture(output)
            (output / "css").mkdir()
            (output / "css/app.css").write_text(
                ".sample { background-image: url(?stale); }\n"
            )
            manifest = release.build_manifest(
                output, EXPECTED_REVISION, ASSET_EPOCH, contract
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
                expected_epoch=ASSET_EPOCH,
                contract=contract,
            )
            (output / "site.webmanifest").write_text('{"name":"a","name":"b"}')
            reference_errors = release.validate_public_references(output, manifest)
        self.assertEqual(len(manifest_errors), 1, manifest_errors)
        self.assertIn("duplicate key", manifest_errors[0])
        self.assertEqual(len(reference_errors), 1, reference_errors)
        self.assertIn("site.webmanifest", reference_errors[0])

    def test_tombstone_resurrection_fails_local_and_live(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            contract, _manifest, _raw = self.make_fixture(output)
            resurrected = output / "tapes/aletheia-memory.tape"
            resurrected.parent.mkdir(parents=True)
            resurrected.write_text("old tape\n")
            manifest = release.build_manifest(
                output, EXPECTED_REVISION, ASSET_EPOCH, contract
            )
            _, errors = release.validate_manifest(
                release.serialize_manifest(manifest),
                output=output,
                expected_revision=EXPECTED_REVISION,
                expected_epoch=ASSET_EPOCH,
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
    @staticmethod
    def repository_manifest() -> dict:
        body = (ROOT / "static/speculation-rules.json").read_bytes()
        digest = hashlib.sha256(body).hexdigest()
        return {
            "resources": [
                {
                    "output_path": "speculation-rules.json",
                    "request_url": (
                        f"/speculation-rules.json?h={digest[:20]}&v={ASSET_EPOCH}"
                    ),
                }
            ]
        }

    def test_repository_headers_are_the_exact_supported_contract(self) -> None:
        contract, errors = headers_contract.validate_headers(
            (ROOT / "_headers").read_text(), self.repository_manifest()
        )
        self.assertEqual(errors, [])
        self.assertIsNotNone(contract)
        self.assertEqual(
            contract.direct_response["speculation-rules"],
            '"/speculation-rules.json?h=dd1ab64ebeb7a41864aa&v=2"',
        )

    def test_missing_wrong_duplicate_extra_and_detach_fail_closed(self) -> None:
        raw = (ROOT / "_headers").read_text()
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


class DeployWorkflowContractTests(unittest.TestCase):
    def test_predeploy_revalidation_follows_wrangler_compile_and_precedes_upload(
        self,
    ) -> None:
        workflow = (ROOT / ".github/workflows/deploy.yml").read_text()
        install = workflow.index("npm install -g wrangler@4.112.0")
        compile_function = workflow.index("wrangler pages functions build functions")
        deploy = workflow.split("- name: Deploy to Cloudflare Pages", 1)[1].split(
            "- name: Verify live authored/runtime boundary", 1
        )[0]
        validate = deploy.index(
            'python3 bin/validate-site.py public --expected-revision "$GITHUB_SHA"'
        )
        upload = deploy.index("wrangler pages deploy --branch=main")
        self.assertLess(install, compile_function)
        self.assertLess(
            compile_function,
            workflow.index("- name: Deploy to Cloudflare Pages"),
        )
        self.assertNotIn("--compatibility-date", workflow)
        self.assertNotIn("wrangler pages deploy public", deploy)
        self.assertLess(validate, upload)
        self.assertIn("GITHUB_SHA: ${{ github.sha }}", deploy)


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
            f"/{pages_runtime.BOUNDARY_NAME}",
            production.REQUIRED_RELEASE_PATHS,
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
            any("Function direct headers differ" in error for error in errors), errors
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
            cast_hash = hashlib.sha256(b"{}\n").hexdigest()[:20]
            cast_url = f"{BASE_URL}{cast}?h={cast_hash}&amp;v={ASSET_EPOCH}"
            system_markup = (
                f'<div data-cast="{cast_url}"></div>'
                f'<link rel="stylesheet" href="/vendor/asciinema/asciinema-player.css?h={CSS_HASH}&amp;v=2">'
                f'<script src="/vendor/asciinema/asciinema-player.min.js?h={JS_HASH}&amp;v=2"></script>'
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
            errors: list[str] = []
            site.validate_asset_contract(
                errors, {system_page: system_markup}, output, ASSET_EPOCH
            )
            site.validate_player_contract(
                errors,
                [(Path("content/systems/demo.md"), cast)],
                html,
                "script-src 'self' 'wasm-unsafe-eval'",
                output,
                static,
                asset_epoch=ASSET_EPOCH,
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
                asset_epoch=ASSET_EPOCH,
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
