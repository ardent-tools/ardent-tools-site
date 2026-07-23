#!/usr/bin/env python3
"""Generate and validate the retained-tree release resource manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import stat
import sys
import tomllib
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urljoin, urlparse

REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
ASSET_EPOCH_RE = re.compile(r"^[1-9][0-9]*$")
DATE_RE = re.compile(r"^20[0-9]{2}-[0-9]{2}-[0-9]{2}$")
OUTPUT_PATH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
MAX_RESOURCES = 1024
MANIFEST_SCHEMA_VERSION = 1
CONTRACT_PATH = Path("release-resources.toml")
BASE_URL = "https://ardent.tools/"
CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)([^)'\"]+)\1\s*\)", re.I)
TEXT_URL_RE = re.compile(r"https://ardent\.tools/[^\s)\]>'\"]+")
HEADER_URL_RE = re.compile(r"[\"'](/[^\"']+)[\"']")
BAD_PERCENT_RE = re.compile(r"%(?![0-9A-Fa-f]{2})")


class ResourceReferenceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[str] = []

    def handle_starttag(self, _tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name in {"href", "src", "content", "data-cast"} and value:
                self.references.append(value)


class JsonLdParser(HTMLParser):
    """Collect raw application/ld+json script bodies.

    Script content is CDATA to the HTML parser: character references are
    never decoded here, so a JSON string keeps its literal query separator
    (a correct &v= or a wrong &amp;v=) exactly as authored.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self._recording = False
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        media_type = (dict(attrs).get("type") or "").split(";", 1)[0].strip().lower()
        if tag == "script" and media_type == "application/ld+json":
            self._recording = True
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._recording:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._recording:
            self._recording = False
            self.blocks.append("".join(self._buffer))

    @property
    def unterminated(self) -> bool:
        return self._recording


def normalized_origin(parsed) -> tuple[str, str, int] | None:
    """Origin triple with the scheme's default port made explicit.

    Implicit and explicit default ports (https://host vs https://host:443)
    normalize identically, so a padded netloc cannot pose as external and
    skip the manifest check. Non-HTTP(S) URLs have no origin here.
    """
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        return None
    hostname = parsed.hostname
    if not hostname:
        return None
    port = parsed.port
    if port is None:
        port = 443 if scheme == "https" else 80
    return scheme, hostname, port


def canonical_resource_path(path: str) -> str:
    """Decode and normalize a same-origin path for manifest-member identity.

    Percent-encoded spellings decode first (strict UTF-8, malformed
    sequences rejected) and dot segments resolve via posixpath.normpath, so
    an alias such as /img/%6cogo-flame.svg or /img/./logo-flame.svg maps to
    the same member it tries to impersonate instead of bypassing the lookup.
    """
    if BAD_PERCENT_RE.search(path):
        raise ValueError(f"malformed percent-encoding in path {path!r}")
    decoded = unquote(path, encoding="utf-8", errors="strict")
    return posixpath.normpath(decoded)


def inspect_manifest_reference(
    errors: list[str], label: str, reference: str, by_path: dict[str, str]
) -> None:
    """Fail when a same-origin reference spells a manifest member inexactly.

    The reference resolves against the site root for member lookup, but only
    the exact root-relative manifest URL or its exact absolute spelling is
    accepted. Aliases that decode or normalize to a member (percent-encoded,
    dot-segment, padded-port, relative, protocol-relative, or otherwise
    re-spelled) are still caught: the lookup is canonical, while acceptance
    compares the authored spelling before URL resolution can erase aliases.
    """
    try:
        resolved = urljoin(BASE_URL, reference)
        parsed = urlparse(resolved)
        origin = normalized_origin(parsed)
    except ValueError:
        errors.append(f"{label}: malformed public resource reference {reference!r}")
        return
    if origin != normalized_origin(urlparse(BASE_URL)):
        return
    try:
        canonical_path = canonical_resource_path(parsed.path)
    except (UnicodeDecodeError, ValueError) as exc:
        errors.append(f"{label}: noncanonical resource path in {reference!r}: {exc}")
        return
    expected = by_path.get(canonical_path)
    if expected is None:
        return
    accepted = {expected, urljoin(BASE_URL, expected)}
    if reference not in accepted:
        errors.append(
            f"{label}: public resource {reference!r} must use manifest URL {expected!r}"
        )


def strict_json_loads(
    raw: str,
    label: str,
    errors: list[str],
    *,
    kind: str = "application/ld+json",
) -> object | None:
    """Parse one JSON document, rejecting extensions and duplicate keys."""

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-JSON constant {value!r}")

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key {key!r}")
            result[key] = value
        return result

    try:
        return json.loads(
            raw, parse_constant=reject_constant, object_pairs_hook=reject_duplicates
        )
    except (ValueError, RecursionError) as exc:
        errors.append(f"{label}: {kind} is not strict JSON: {exc}")
        return None


def validate_json_ld_block(
    errors: list[str], label: str, raw: str, by_path: dict[str, str]
) -> None:
    """Strict-parse one JSON-LD block and inspect every string."""
    document = strict_json_loads(raw, label, errors)
    if document is None:
        return
    pending: list[object] = [document]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
        elif isinstance(value, str):
            inspect_manifest_reference(errors, label, value, by_path)


def read_contract(path: Path = CONTRACT_PATH) -> tuple[dict, list[str]]:
    errors: list[str] = []
    try:
        contract = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return {}, [f"{path}: cannot read release contract: {exc}"]
    if set(contract) != {
        "schema_version",
        "manifest_name",
        "canonical_paths",
        "tombstones",
    }:
        errors.append(f"{path}: release contract has unexpected or missing keys")
    if contract.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        errors.append(f"{path}: schema_version must be {MANIFEST_SCHEMA_VERSION}")
    manifest_name = contract.get("manifest_name")
    if manifest_name != "release-resources.json":
        errors.append(f"{path}: manifest_name must be 'release-resources.json'")
    canonical = contract.get("canonical_paths")
    if not isinstance(canonical, list) or not canonical:
        errors.append(f"{path}: canonical_paths must be a nonempty array")
    elif len(canonical) != len(set(canonical)):
        errors.append(f"{path}: canonical_paths contains duplicates")
    else:
        for value in canonical:
            if not valid_output_path(value):
                errors.append(f"{path}: invalid canonical path {value!r}")
    tombstones = contract.get("tombstones")
    if not isinstance(tombstones, list) or not tombstones:
        errors.append(f"{path}: tombstones must be a nonempty array")
    else:
        seen: set[str] = set()
        for item in tombstones:
            if not isinstance(item, dict) or set(item) != {
                "path",
                "retain_through",
                "reason",
            }:
                errors.append(f"{path}: each tombstone must have path, retain_through, and reason")
                continue
            tombstone_path = item.get("path")
            if not isinstance(tombstone_path, str) or not valid_request_path(tombstone_path):
                errors.append(f"{path}: invalid tombstone path {tombstone_path!r}")
            elif tombstone_path in seen:
                errors.append(f"{path}: duplicate tombstone path {tombstone_path!r}")
            else:
                seen.add(tombstone_path)
            if not isinstance(item.get("retain_through"), str) or not DATE_RE.fullmatch(
                item["retain_through"]
            ):
                errors.append(f"{path}: tombstone retain_through must be YYYY-MM-DD")
            if not isinstance(item.get("reason"), str) or not item["reason"].strip():
                errors.append(f"{path}: tombstone reason must be nonempty")
    return contract, errors


def valid_output_path(value: object) -> bool:
    if (
        not isinstance(value, str)
        or not value
        or value.startswith(("/", "."))
        or not OUTPUT_PATH_RE.fullmatch(value)
    ):
        return False
    if "\\" in value or "//" in value:
        return False
    path = PurePosixPath(value)
    return all(part not in {"", ".", ".."} for part in path.parts)


def valid_request_path(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("/") or value.startswith("//"):
        return False
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or "\\" in parsed.path:
        return False
    return valid_output_path(parsed.path.lstrip("/"))


def public_files(output: Path, manifest_name: str) -> list[Path]:
    files: list[Path] = []
    for path in sorted(output.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"public artifact must not be a symlink: {path.relative_to(output)}")
        if not path.exists() or not stat.S_ISREG(path.lstat().st_mode):
            continue
        relative = path.relative_to(output).as_posix()
        if relative in {"_headers", "_redirects", manifest_name} or relative.endswith(".html"):
            continue
        files.append(path)
    return files


def request_url(output_path: str, digest: str, asset_epoch: str, canonical: set[str]) -> str:
    path = f"/{output_path}"
    if output_path in canonical:
        return path
    return f"{path}?h={digest[:20]}&v={asset_epoch}"


def build_manifest(
    output: Path, revision: str, asset_epoch: str, contract: dict
) -> dict:
    if not REVISION_RE.fullmatch(revision):
        raise ValueError("revision must be exactly one lowercase 40-hex value")
    if not ASSET_EPOCH_RE.fullmatch(asset_epoch):
        raise ValueError("asset epoch must be a nonzero decimal string")
    manifest_name = contract["manifest_name"]
    canonical = set(contract["canonical_paths"])
    resources: list[dict[str, str]] = []
    for path in public_files(output, manifest_name):
        relative = path.relative_to(output).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        resources.append(
            {
                "request_url": request_url(relative, digest, asset_epoch, canonical),
                "output_path": relative,
                "sha256": digest,
            }
        )
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "revision": revision,
        "asset_epoch": asset_epoch,
        "resource_count": len(resources),
        "resources": resources,
        "tombstones": contract["tombstones"],
    }


def serialize_manifest(manifest: dict) -> bytes:
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")


def validate_public_references(output: Path, manifest: dict) -> list[str]:
    """Require every authored reference to a manifest member to use its exact URL.

    Coverage: HTML element attributes (entity-decoded by the parser, so the
    authored &amp;v= separator compares as &v=), every string inside each
    application/ld+json block (strict JSON, raw text), CSS url() targets,
    site.webmanifest JSON strings, agent-facing text files, and _headers
    resource values.
    """
    errors: list[str] = []
    by_path = {
        f"/{item['output_path']}": item["request_url"]
        for item in manifest.get("resources", [])
        if isinstance(item, dict)
        and isinstance(item.get("output_path"), str)
        and isinstance(item.get("request_url"), str)
    }

    for path in sorted(output.rglob("*.html")):
        text = path.read_text()
        label = str(path.relative_to(output))
        parser = ResourceReferenceParser()
        parser.feed(text)
        parser.close()
        for reference in parser.references:
            inspect_manifest_reference(errors, label, reference, by_path)
        ld_parser = JsonLdParser()
        ld_parser.feed(text)
        ld_parser.close()
        if ld_parser.unterminated:
            errors.append(f"{label}: unterminated application/ld+json block")
        for block in ld_parser.blocks:
            validate_json_ld_block(errors, label, block, by_path)
    for path in sorted(output.rglob("*.css")):
        for match in CSS_URL_RE.finditer(path.read_text()):
            inspect_manifest_reference(
                errors, str(path.relative_to(output)), match.group(2), by_path
            )
    webmanifest = output / "site.webmanifest"
    if webmanifest.is_file():
        document = strict_json_loads(
            webmanifest.read_text(),
            "site.webmanifest",
            errors,
            kind="document",
        )
        if document is not None:
            pending: list[object] = [document]
            while pending:
                value = pending.pop()
                if isinstance(value, dict):
                    pending.extend(value.values())
                elif isinstance(value, list):
                    pending.extend(value)
                elif isinstance(value, str):
                    inspect_manifest_reference(errors, "site.webmanifest", value, by_path)
    for relative in ("llms.txt", "robots.txt"):
        path = output / relative
        if path.is_file():
            for match in TEXT_URL_RE.finditer(path.read_text()):
                inspect_manifest_reference(errors, relative, match.group(0), by_path)
    headers = output / "_headers"
    if headers.is_file():
        for match in HEADER_URL_RE.finditer(headers.read_text()):
            inspect_manifest_reference(errors, "_headers", match.group(1), by_path)
    return errors


def validate_manifest(
    raw: bytes,
    *,
    output: Path,
    expected_revision: str,
    expected_epoch: str,
    contract: dict,
) -> tuple[dict, list[str]]:
    errors: list[str] = []
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        return {}, [f"release manifest is not strict UTF-8 JSON: {exc}"]
    manifest = strict_json_loads(
        text,
        "release manifest",
        errors,
        kind="document",
    )
    if manifest is None:
        return {}, errors
    if not isinstance(manifest, dict) or set(manifest) != {
        "schema_version",
        "revision",
        "asset_epoch",
        "resource_count",
        "resources",
        "tombstones",
    }:
        return {}, ["release manifest has unexpected or missing top-level keys"]
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        errors.append(f"release manifest schema_version must be {MANIFEST_SCHEMA_VERSION}")
    if manifest.get("revision") != expected_revision:
        errors.append(
            f"release manifest revision mismatch: expected {expected_revision}, "
            f"found {manifest.get('revision')!r}"
        )
    if manifest.get("asset_epoch") != expected_epoch:
        errors.append(
            f"release manifest asset_epoch mismatch: expected {expected_epoch!r}, "
            f"found {manifest.get('asset_epoch')!r}"
        )
    resources = manifest.get("resources")
    if not isinstance(resources, list):
        return manifest, errors + ["release manifest resources must be an array"]
    if not 1 <= len(resources) <= MAX_RESOURCES:
        errors.append(
            f"release manifest resource count {len(resources)} is outside 1..{MAX_RESOURCES}"
        )
    if (
        not isinstance(manifest.get("resource_count"), int)
        or isinstance(manifest.get("resource_count"), bool)
        or manifest["resource_count"] != len(resources)
    ):
        errors.append("release manifest resource_count does not equal resources length")
    manifest_name = contract["manifest_name"]
    canonical = set(contract["canonical_paths"])
    expected_paths: set[str]
    try:
        expected_paths = {
            path.relative_to(output).as_posix() for path in public_files(output, manifest_name)
        }
    except ValueError as exc:
        errors.append(str(exc))
        expected_paths = set()
    seen_paths: set[str] = set()
    seen_urls: set[str] = set()
    for index, item in enumerate(resources):
        label = f"release manifest resources[{index}]"
        if not isinstance(item, dict) or set(item) != {"request_url", "output_path", "sha256"}:
            errors.append(f"{label} must contain only request_url, output_path, and sha256")
            continue
        output_path = item.get("output_path")
        url = item.get("request_url")
        digest = item.get("sha256")
        if not valid_output_path(output_path):
            errors.append(f"{label} has invalid output_path {output_path!r}")
            continue
        if output_path in seen_paths:
            errors.append(f"release manifest repeats output_path {output_path!r}")
        seen_paths.add(output_path)
        if not isinstance(digest, str) or not DIGEST_RE.fullmatch(digest):
            errors.append(f"{label} has malformed sha256 {digest!r}")
            continue
        if not isinstance(url, str) or url in seen_urls:
            errors.append(f"{label} has missing or duplicate request_url {url!r}")
        else:
            seen_urls.add(url)
        expected_url = request_url(output_path, digest, expected_epoch, canonical)
        if url != expected_url:
            errors.append(f"{label} request_url must be {expected_url!r}, found {url!r}")
        artifact = output / output_path
        try:
            artifact.relative_to(output)
        except ValueError:
            errors.append(f"{label} escapes the retained artifact root")
            continue
        if not artifact.is_file() or artifact.is_symlink():
            errors.append(f"{label} does not resolve to a regular retained artifact")
        elif hashlib.sha256(artifact.read_bytes()).hexdigest() != digest:
            errors.append(f"{label} sha256 does not match retained artifact bytes")
    if seen_paths != expected_paths:
        missing = sorted(expected_paths - seen_paths)
        extra = sorted(seen_paths - expected_paths)
        errors.append(f"release manifest coverage differs; missing={missing}, extra={extra}")
    missing_canonical = sorted(canonical - expected_paths)
    if missing_canonical:
        errors.append(f"release contract canonical paths are absent: {missing_canonical}")
    tombstones = manifest.get("tombstones")
    if tombstones != contract["tombstones"]:
        errors.append("release manifest tombstones differ from release-resources.toml")
    for item in tombstones if isinstance(tombstones, list) else []:
        path = item.get("path") if isinstance(item, dict) else None
        if isinstance(path, str) and path.lstrip("/") in expected_paths:
            errors.append(f"tombstone is present in retained artifact: {path}")
    return manifest, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path, help="already-built retained public tree")
    parser.add_argument("--revision", required=True)
    parser.add_argument("--asset-epoch", required=True)
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    args = parser.parse_args()
    contract, errors = read_contract(args.contract)
    if errors:
        for error in errors:
            sys.stderr.write(f"ERROR: {error}\n")
        return 1
    try:
        manifest = build_manifest(args.output.resolve(), args.revision, args.asset_epoch, contract)
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"ERROR: cannot generate release manifest: {exc}\n")
        return 1
    destination = args.output / contract["manifest_name"]
    destination.write_bytes(serialize_manifest(manifest))
    _, errors = validate_manifest(
        destination.read_bytes(),
        output=args.output.resolve(),
        expected_revision=args.revision,
        expected_epoch=args.asset_epoch,
        contract=contract,
    )
    if errors:
        for error in errors:
            sys.stderr.write(f"ERROR: {error}\n")
        return 1
    sys.stdout.write(
        f"PASS: release manifest covers {manifest['resource_count']} served non-HTML resources\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
