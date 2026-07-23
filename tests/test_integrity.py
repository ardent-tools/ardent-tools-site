"""Focused regressions for release identity, cache, tape, and player contracts."""

from __future__ import annotations

import hashlib
import importlib.util
import shutil
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
catalog = load_script("ardent_generate_catalog", "generate-systems-json.py")
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
    f'<link rel="stylesheet" href="{CSS_URL}">'
    f'<script src="{JS_URL}" defer></script>'
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
    tombstone_status: int = 404,
    tombstone_cache: str = GOOD_CACHE,
    live_manifest_body: bytes | None = None,
    resource_overrides: dict[str, tuple[int, str, bytes]] | None = None,
    redirect_statuses: dict[str, int] | None = None,
    redirect_targets: dict[str, str] | None = None,
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
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory)
        files = {
            "atom.xml": b"<feed/>\n",
            "build-revision.txt": f"{EXPECTED_REVISION}\n".encode(),
            "css/site.css": CSS_BODY,
            "js/site.js": JS_BODY,
            "js/error.js": ERROR_JS_BODY,
            "llms.txt": b"release fixture\n",
            "robots.txt": b"User-agent: *\n",
            "site.webmanifest": b"{}\n",
            "sitemap.xml": sitemap_body,
            "speculation-rules.json": b"{}\n",
            "systems.json": b"[]\n",
        }
        for relative, body in files.items():
            path = output / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        contract, contract_errors = release.read_contract(ROOT / "release-resources.toml")
        test.assertEqual(contract_errors, [])
        manifest = release.build_manifest(output, EXPECTED_REVISION, ASSET_EPOCH, contract)
        manifest_bytes = release.serialize_manifest(manifest)
        (output / contract["manifest_name"]).write_bytes(manifest_bytes)

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
            responses[(url, False)] = (status, {"Cache-Control": cache}, body)

        responses[(f"{BASE_URL}/{contract['manifest_name']}", False)] = (
            200,
            {"Cache-Control": GOOD_CACHE},
            manifest_bytes if live_manifest_body is None else live_manifest_body,
        )
        page_headers = {"Cache-Control": GOOD_CACHE, "Content-Security-Policy": GOOD_CSP}
        responses[(f"{BASE_URL}/", False)] = (
            200,
            page_headers,
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
            {"cache-control": GOOD_CACHE, "content-security-policy": GOOD_CSP},
            (
                f'<link rel="canonical" href="{BASE_URL}/evidence/">'
                "Evidence register 0 published casts."
                f"{assets}"
            ).encode(),
        )
        missing_path = production.missing_probe_path(EXPECTED_REVISION)
        default_404 = (
            "404: no such path Return home "
            f'<link rel="stylesheet" href="{CSS_URL}">'
            f'<script src="{ERROR_JS_URL}" defer></script>'
        ).encode()
        responses[(f"{BASE_URL}{missing_path}", False)] = (
            custom_404_status,
            {
                "Cache-Control": custom_404_cache,
                "Content-Security-Policy": custom_404_csp,
            },
            default_404 if custom_404_body is None else custom_404_body,
        )
        for tombstone in manifest["tombstones"]:
            responses[(f"{BASE_URL}{tombstone['path']}", False)] = (
                tombstone_status,
                {"Cache-Control": tombstone_cache},
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
            )
        test.assertEqual(responses, {}, f"required URLs were not requested: {responses!r}")
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
        self.assertTrue(any("release resource digest mismatch" in error for error in errors), errors)
        self.assertTrue(
            any("authored JavaScript asset digest mismatch" in error for error in errors), errors
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


class ProductionRouteContractTests(unittest.TestCase):
    def test_custom_404_probe_is_revision_specific_and_disjoint(self) -> None:
        path = production.missing_probe_path(EXPECTED_REVISION)
        self.assertEqual(path, production.missing_probe_path(EXPECTED_REVISION))
        self.assertNotEqual(path, production.missing_probe_path("3" * 40))
        self.assertRegex(path, r"^/__ardent-missing-[0-9a-f]{24}/$")
        errors: list[str] = []
        self.assertTrue(production.missing_probe_is_disjoint(errors, path, ["/", "/about/"]))
        self.assertEqual(errors, [])

    def test_custom_404_probe_collision_fails_closed(self) -> None:
        path = production.missing_probe_path(EXPECTED_REVISION)
        errors: list[str] = []
        self.assertFalse(production.missing_probe_is_disjoint(errors, path, ["/", path]))
        self.assertIn("collides with sitemap route", errors[0])

    def test_custom_404_wrong_status_and_missing_marker_fail(self) -> None:
        errors = run_production_fixture(
            self,
            custom_404_status=200,
            custom_404_body=("Return home " + ASSET_MARKUP).encode(),
        )
        self.assertTrue(any("expected exact 404" in error for error in errors), errors)
        self.assertTrue(any("lacks custom 404 marker '404: no such path'" in error for error in errors), errors)

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
        self.assertTrue(any("Cache-Control must be exactly" in error for error in errors), errors)
        self.assertTrue(any("strict zero-cast CSP differs" in error for error in errors), errors)
        self.assertTrue(any("Cloudflare email-protection" in error for error in errors), errors)

    def test_custom_404_malformed_asset_epoch_fails(self) -> None:
        malformed = (
            "404: no such path Return home "
            f'<link rel="stylesheet" href="{CSS_URL}">'
            f'<script src="/js/site.js?h={JS_HASH}&v=1"></script>'
        ).encode()
        errors = run_production_fixture(self, custom_404_body=malformed)
        self.assertTrue(any("expected '2'" in error for error in errors), errors)

    def test_custom_404_only_asset_stale_bytes_fail_digest(self) -> None:
        errors = run_production_fixture(self, error_js_body=b"stale custom 404 script\n")
        self.assertTrue(
            any("release resource digest mismatch" in error and "/js/error.js" in error for error in errors),
            errors,
        )
        self.assertTrue(
            any("authored JavaScript asset digest mismatch" in error and ERROR_JS_URL in error for error in errors),
            errors,
        )

    def test_canonical_route_redirect_cannot_hide(self) -> None:
        errors = run_production_fixture(self, about_status=301)
        self.assertTrue(any("/about/ returned 301, expected direct 200" in error for error in errors), errors)

    def test_canonical_route_rewrite_to_root_body_cannot_hide(self) -> None:
        root_body = (
            f'<link rel="canonical" href="{BASE_URL}/">Root body{ASSET_MARKUP}'
        ).encode()
        errors = run_production_fixture(self, about_body=root_body)
        self.assertTrue(any("canonical resolves" in error and "/about/" in error for error in errors), errors)


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
        self.assertRegex(
            probes["/systems/ergon-tools/*"],
            r"^/systems/ergon-tools/__ardent-probe-[0-9a-f]{24}$",
        )
        self.assertRegex(
            probes["/systems/nosologia/*"],
            r"^/systems/nosologia/__ardent-probe-[0-9a-f]{24}$",
        )
        alternate = redirects.redirect_probe_path(
            redirects.SUPPORTED_REDIRECTS[0],
            "3" * 40,
        )
        self.assertNotEqual(probes["/systems/ergon-tools/*"], alternate)

    def test_each_supported_declaration_omission_fails(self) -> None:
        declarations = [
            rule.declaration for rule in redirects.SUPPORTED_REDIRECTS
        ]
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
        base = "\n".join(
            rule.declaration for rule in redirects.SUPPORTED_REDIRECTS
        )
        cases = {
            "extra": (base + "\n/extra /evidence/ 301", "unsupported extra"),
            "duplicate": (
                base + "\n/demos /evidence/ 301",
                "duplicate redirect declaration",
            ),
            "malformed": (base + "\n/broken /evidence/", "malformed redirect declaration"),
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
        contract, contract_errors = release.read_contract(ROOT / "release-resources.toml")
        self.assertEqual(contract_errors, [])
        bodies = {
            "atom.xml": b"<feed/>\n",
            "build-revision.txt": f"{EXPECTED_REVISION}\n".encode(),
            "llms.txt": b"fixture\n",
            "robots.txt": b"fixture\n",
            "sitemap.xml": b"<urlset/>\n",
            "files/report.pdf": b"pdf bytes\n",
        }
        for relative, body in bodies.items():
            path = output / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        manifest = release.build_manifest(output, EXPECTED_REVISION, ASSET_EPOCH, contract)
        return contract, manifest, release.serialize_manifest(manifest)

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
            manifest["resources"][1]["request_url"] = manifest["resources"][0]["request_url"]
            _, errors = release.validate_manifest(
                release.serialize_manifest(manifest),
                output=output,
                expected_revision=EXPECTED_REVISION,
                expected_epoch=ASSET_EPOCH,
                contract=contract,
            )
        self.assertTrue(any("resource_count" in error for error in errors), errors)
        self.assertTrue(any("duplicate request_url" in error for error in errors), errors)

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
        self.assertTrue(any("sha256 does not match" in error for error in stale_errors), stale_errors)
        self.assertTrue(any("does not resolve" in error for error in missing_errors), missing_errors)
        self.assertTrue(any("coverage differs" in error for error in missing_errors), missing_errors)

    def test_unversioned_public_artifact_reference_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            _contract, manifest, _raw = self.make_fixture(output)
            (output / "index.html").write_text(
                '<a href="/files/report.pdf">Download report</a>'
            )
            errors = release.validate_public_references(output, manifest)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("must use manifest URL", errors[0])

    def test_unversioned_css_manifest_and_header_references_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            _contract, manifest, _raw = self.make_fixture(output)
            (output / "css").mkdir()
            (output / "css/app.css").write_text("body { background: url('/files/report.pdf'); }\n")
            (output / "site.webmanifest").write_text('{"icons":[{"src":"/files/report.pdf"}]}\n')
            (output / "_headers").write_text('/*\n  Example-Resource: "/files/report.pdf"\n')
            errors = release.validate_public_references(output, manifest)
        self.assertEqual(len(errors), 3, errors)
        self.assertTrue(all("must use manifest URL" in error for error in errors), errors)

    def test_tombstone_resurrection_fails_local_and_live(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            contract, _manifest, _raw = self.make_fixture(output)
            resurrected = output / "tapes/aletheia-memory.tape"
            resurrected.parent.mkdir(parents=True)
            resurrected.write_text("old tape\n")
            manifest = release.build_manifest(output, EXPECTED_REVISION, ASSET_EPOCH, contract)
            _, errors = release.validate_manifest(
                release.serialize_manifest(manifest),
                output=output,
                expected_revision=EXPECTED_REVISION,
                expected_epoch=ASSET_EPOCH,
                contract=contract,
            )
        self.assertTrue(any("tombstone is present" in error for error in errors), errors)
        live_errors = run_production_fixture(self, tombstone_status=200)
        self.assertTrue(any("tombstone /tapes/aletheia-memory.tape returned 200" in error for error in live_errors), live_errors)

    def test_live_manifest_and_structured_body_mismatch_fail(self) -> None:
        errors = run_production_fixture(
            self,
            live_manifest_body=b"{}\n",
            resource_overrides={"systems.json": (200, GOOD_CACHE, b"stale systems\n")},
        )
        self.assertTrue(any("live /release-resources.json bytes differ" in error for error in errors), errors)
        self.assertTrue(any("/systems.json" in error and "digest mismatch" in error for error in errors), errors)

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
