#!/usr/bin/env python3
"""Derive the build-provenance CycloneDX SBOM from its live pin authorities."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOM_FORMAT = "CycloneDX"
SPEC_VERSION = "1.6"
GENERATOR_VERSION = 1
DEPLOY_WORKFLOW = Path(".github/workflows/deploy.yml")
PACKAGE_LOCK = Path("package-lock.json")
PYTHON_REQUIREMENTS = Path("bin/requirements.txt")
COLOPHON = Path("content/colophon.md")
PLAYER_JS = Path("static/vendor/asciinema/asciinema-player.min.js")
PLAYER_CSS = Path("static/vendor/asciinema/asciinema-player.css")

# WHY: bin/requirements.txt is hash-locked but carries no license field;
# these are verified against each package's own PyPI info.license_expression.
PYTHON_LICENSES = {
    "attrs": "MIT",
    "jsonschema": "MIT",
    "jsonschema-specifications": "MIT",
    "referencing": "MIT",
    "rpds-py": "MIT",
    "typing-extensions": "PSF-2.0",
}
# WHY: the pinned workflow carries the commit and version comment, not the
# license; these are verified against each action repo's GitHub API spdx_id.
ACTION_LICENSES = {
    "actions/checkout": "MIT",
    "actions/setup-python": "MIT",
    "actions/setup-node": "MIT",
}
NPM_COMPONENTS = ("@playwright/test", "pa11y-ci", "wrangler")
PLAYER_VERSION_RE = re.compile(
    r"\[asciinema-player\]\([^)]*\)\s+v(\d+\.\d+\.\d+)\s+is vendored"
)
NPM_BOUNDARY_RE = re.compile(r"npm toolchain packages \(([^)]*)\)")
ZOLA_SHA_RE = re.compile(r"ZOLA_SHA256:\s*([0-9a-f]{64})")
ZOLA_VERSION_RE = re.compile(
    r"getzola/zola/releases/download/v(\d+\.\d+\.\d+)/zola-v\1-x86_64"
)
TYPST_VERSION_RE = re.compile(r"TYPST_VERSION:\s*(\d+\.\d+\.\d+)")
TYPST_SHA_RE = re.compile(r"TYPST_SHA256:\s*([0-9a-f]{64})")
LYCHEE_VERSION_RE = re.compile(r"LYCHEE_VERSION:\s*(\d+\.\d+\.\d+)")
LYCHEE_SHA_RE = re.compile(r"LYCHEE_SHA256:\s*([0-9a-f]{64})")
ACTION_PIN_RE = re.compile(
    r"uses:\s*(actions/[a-z0-9-]+)@([0-9a-f]{40})\s*#\s*(v[0-9][\w.]*)"
)
PYTHON_VERSION_RE = re.compile(r"python-version:\s*'(\d+\.\d+)'")
REQUIREMENTS_PIN_RE = re.compile(
    r"^([A-Za-z][A-Za-z0-9._-]*)==([0-9][A-Za-z0-9.]*)", re.MULTILINE
)


def read_text(root: Path, relative: Path) -> str:
    path = root / relative
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"{relative}: cannot read pin authority: {exc}") from exc


def require_match(pattern: re.Pattern, text: str, label: str) -> str:
    match = pattern.search(text)
    if match is None:
        raise SystemExit(f"{label}: no match for {pattern.pattern!r}")
    return match.group(1)


def pypi_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def license_field(spdx: str) -> dict:
    if " OR " in spdx or " AND " in spdx:
        return {"expression": spdx}
    return {"license": {"id": spdx}}


def asset_property(root: Path, relative: Path) -> dict:
    digest = hashlib.sha256((root / relative).read_bytes()).hexdigest()
    return {"name": "ardent:asset", "value": f"{relative.as_posix()}#sha256:{digest}"}


def player_component(root: Path) -> dict:
    colophon = read_text(root, COLOPHON)
    version = require_match(PLAYER_VERSION_RE, colophon, COLOPHON.as_posix())
    purl = f"pkg:npm/asciinema-player@{version}"
    return {
        "type": "library",
        "bom-ref": purl,
        "name": "asciinema-player",
        "version": version,
        "purl": purl,
        "scope": "required",
        "licenses": [license_field("Apache-2.0")],
        "properties": [
            {"name": "ardent:tier", "value": "runtime"},
            asset_property(root, PLAYER_JS),
            asset_property(root, PLAYER_CSS),
        ],
    }


def tool_component(
    *, name: str, namespace: str, tag: str, version: str, sha256: str, license_id: str
) -> dict:
    purl = f"pkg:github/{namespace}/{name}@{tag}"
    return {
        "type": "application",
        "bom-ref": purl,
        "name": name,
        "version": version,
        "purl": purl,
        "scope": "optional",
        "hashes": [{"alg": "SHA-256", "content": sha256}],
        "licenses": [license_field(license_id)],
        "properties": [{"name": "ardent:tier", "value": "build"}],
    }


def build_toolchain_components(deploy_yml: str) -> list[dict]:
    zola_version = require_match(ZOLA_VERSION_RE, deploy_yml, "deploy.yml zola version")
    zola_sha = require_match(ZOLA_SHA_RE, deploy_yml, "deploy.yml zola sha256")
    typst_version = require_match(TYPST_VERSION_RE, deploy_yml, "deploy.yml typst version")
    typst_sha = require_match(TYPST_SHA_RE, deploy_yml, "deploy.yml typst sha256")
    lychee_version = require_match(
        LYCHEE_VERSION_RE, deploy_yml, "deploy.yml lychee version"
    )
    lychee_sha = require_match(LYCHEE_SHA_RE, deploy_yml, "deploy.yml lychee sha256")
    return [
        tool_component(
            name="zola",
            namespace="getzola",
            tag=f"v{zola_version}",
            version=zola_version,
            sha256=zola_sha,
            license_id="EUPL-1.2",
        ),
        tool_component(
            name="typst",
            namespace="typst",
            tag=f"v{typst_version}",
            version=typst_version,
            sha256=typst_sha,
            license_id="Apache-2.0",
        ),
        tool_component(
            name="lychee",
            namespace="lycheeverse",
            tag=f"lychee-v{lychee_version}",
            version=lychee_version,
            sha256=lychee_sha,
            license_id="Apache-2.0 OR MIT",
        ),
    ]


def action_components(deploy_yml: str) -> list[dict]:
    pins = {name: (sha, tag) for name, sha, tag in ACTION_PIN_RE.findall(deploy_yml)}
    if set(pins) != set(ACTION_LICENSES):
        raise SystemExit(
            "deploy.yml action pin set differs from the closed authority; "
            f"expected={sorted(ACTION_LICENSES)}, found={sorted(pins)}"
        )
    components = []
    for name in sorted(ACTION_LICENSES):
        sha, tag = pins[name]
        purl = f"pkg:github/{name}@{sha}"
        components.append(
            {
                "type": "application",
                "bom-ref": purl,
                "name": name,
                "version": tag,
                "purl": purl,
                "scope": "optional",
                "licenses": [license_field(ACTION_LICENSES[name])],
                "properties": [{"name": "ardent:tier", "value": "build"}],
            }
        )
    return components


def python_interpreter_component(deploy_yml: str) -> dict:
    matches = sorted(set(PYTHON_VERSION_RE.findall(deploy_yml)))
    if len(matches) != 1:
        raise SystemExit(
            f"deploy.yml python-version pins must be exactly one value, found {matches!r}"
        )
    version = matches[0]
    purl = f"pkg:generic/python@{version}"
    return {
        "type": "platform",
        "bom-ref": purl,
        "name": "python",
        "version": version,
        "purl": purl,
        "scope": "optional",
        "properties": [{"name": "ardent:tier", "value": "build"}],
    }


def verify_npm_boundary_claim(root: Path) -> None:
    # WARNING: NPM_COMPONENTS is the closed authority for npm coverage; the
    # colophon states that exact boundary in prose (issue #101 found the two
    # disagreeing - the colophon claimed lockfile-wide coverage while this
    # generator only ever emitted these three named packages). Fail loudly
    # the moment either side changes without the other.
    colophon = read_text(root, COLOPHON)
    match = NPM_BOUNDARY_RE.search(colophon)
    if match is None:
        raise SystemExit(
            f"{COLOPHON}: no \"npm toolchain packages (...)\" boundary claim "
            "found; state the exact npm coverage boundary in backticks"
        )
    claimed = tuple(sorted(re.findall(r"`([^`]+)`", match.group(1))))
    actual = tuple(sorted(NPM_COMPONENTS))
    if claimed != actual:
        raise SystemExit(
            f"{COLOPHON}: npm boundary claim {claimed!r} does not match "
            f"generate-sbom.py NPM_COMPONENTS {actual!r} - update whichever "
            "one is stale"
        )


def npm_components(root: Path) -> list[dict]:
    document = json.loads(read_text(root, PACKAGE_LOCK))
    packages = document.get("packages", {})
    components = []
    for name in NPM_COMPONENTS:
        entry = packages.get(f"node_modules/{name}")
        if not isinstance(entry, dict):
            raise SystemExit(f"package-lock.json: missing node_modules/{name}")
        version = entry.get("version")
        license_id = entry.get("license")
        if not isinstance(version, str) or not version:
            raise SystemExit(f"package-lock.json: node_modules/{name} has no version")
        if not isinstance(license_id, str) or not license_id:
            raise SystemExit(f"package-lock.json: node_modules/{name} has no license")
        purl = f"pkg:npm/{name.replace('@', '%40', 1)}@{version}"
        components.append(
            {
                "type": "library",
                "bom-ref": purl,
                "name": name,
                "version": version,
                "purl": purl,
                "scope": "optional",
                "licenses": [license_field(license_id)],
                "properties": [{"name": "ardent:tier", "value": "build"}],
            }
        )
    return components


def python_dependency_components(root: Path) -> list[dict]:
    requirements = read_text(root, PYTHON_REQUIREMENTS)
    pins = REQUIREMENTS_PIN_RE.findall(requirements)
    if not pins:
        raise SystemExit(f"{PYTHON_REQUIREMENTS}: no name==version pins found")
    components = []
    for name, version in pins:
        license_id = PYTHON_LICENSES.get(name)
        if license_id is None:
            raise SystemExit(
                f"{PYTHON_REQUIREMENTS}: {name} has no entry in the closed "
                "PYTHON_LICENSES authority; verify its PyPI license and add one"
            )
        purl = f"pkg:pypi/{pypi_name(name)}@{version}"
        components.append(
            {
                "type": "library",
                "bom-ref": purl,
                "name": name,
                "version": version,
                "purl": purl,
                "scope": "optional",
                "licenses": [license_field(license_id)],
                "properties": [{"name": "ardent:tier", "value": "build"}],
            }
        )
    return components


def source_provenance(root: Path) -> list[dict]:
    sources = [
        DEPLOY_WORKFLOW,
        PACKAGE_LOCK,
        PYTHON_REQUIREMENTS,
        COLOPHON,
        PLAYER_JS,
        PLAYER_CSS,
    ]
    properties = []
    for relative in sources:
        digest = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        properties.append(
            {"name": "ardent:source", "value": f"{relative.as_posix()}#sha256:{digest}"}
        )
    return properties


def build_bom(root: Path = ROOT) -> dict:
    deploy_yml = read_text(root, DEPLOY_WORKFLOW)
    verify_npm_boundary_claim(root)
    components = [
        player_component(root),
        *build_toolchain_components(deploy_yml),
        *action_components(deploy_yml),
        python_interpreter_component(deploy_yml),
        *npm_components(root),
        *python_dependency_components(root),
    ]
    return {
        "bomFormat": BOM_FORMAT,
        "specVersion": SPEC_VERSION,
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "bom-ref": "ardent-tools-site",
                "name": "ardent-tools-site",
            },
            "properties": [
                {"name": "ardent:generator", "value": "bin/generate-sbom.py"},
                {"name": "ardent:generator_version", "value": str(GENERATOR_VERSION)},
                {
                    "name": "ardent:purpose",
                    "value": (
                        "Build-provenance and product-composition receipt. Covers "
                        "the one runtime-shipped third-party dependency and the "
                        "pinned build toolchain; the toolchain itself never ships "
                        "to a visitor's browser."
                    ),
                },
                *source_provenance(root),
            ],
        },
        "components": components,
    }


def serialize_bom(document: dict) -> bytes:
    return (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def display_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def check_output(path: Path, expected: bytes, root: Path = ROOT) -> bool:
    try:
        actual = path.read_bytes()
    except OSError:
        actual = b""
    if actual == expected:
        return True
    sys.stderr.write(
        f"ERROR: stale generated artifact: {display_path(path, root)}; "
        "run `python3 bin/site.py sync`\n"
    )
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("static/sbom.cdx.json"),
        help="destination relative to --root (defaults to static/sbom.cdx.json)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare the destination with a fresh derivation instead of writing",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    expected = serialize_bom(build_bom(root))
    if args.check:
        return 0 if check_output(output, expected, root) else 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
