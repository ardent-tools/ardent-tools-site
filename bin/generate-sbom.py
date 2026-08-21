#!/usr/bin/env python3
"""Derive the build-provenance CycloneDX SBOM from its live pin authorities."""

from __future__ import annotations

import argparse
import base64
import binascii
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
# WHY a named tuple, not inlined at each call site: bin/git-hooks/pre-commit queries
# this exact set via --list-sources so a staged change outside it costs the hook
# nothing (#136) - one authority for "what can make the SBOM stale", not a second
# hand-maintained copy in the hook.
SBOM_SOURCES = (
    DEPLOY_WORKFLOW,
    PACKAGE_LOCK,
    PYTHON_REQUIREMENTS,
    COLOPHON,
    PLAYER_JS,
    PLAYER_CSS,
)

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
# WHY these three are named: they are the lockfile's ROOTS, not its boundary.
# Every package below is emitted (forkwright#101); these say which execution
# tier a package inherits by being reachable from one of them. A package
# reachable from two roots carries two tiers, because it genuinely runs in
# both and collapsing that to one would be a tidier lie.
NPM_TIER_ROOTS = {
    "wrangler": "deploy",
    "@playwright/test": "test",
    "pa11y-ci": "test",
}
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
    """The colophon must claim exactly the coverage this generator produces.

    WHY it is checked rather than trusted: forkwright#101 found the two
    disagreeing in the direction that flatters — the colophon described a
    lockfile-derived bill of materials while the generator emitted three named
    packages. The coverage is now genuinely lockfile-wide, so the claim the
    colophon must carry is the count, and a count is checkable.
    """
    colophon = read_text(root, COLOPHON)
    match = NPM_BOUNDARY_RE.search(colophon)
    if match is None:
        raise SystemExit(
            f"{COLOPHON}: no \"npm toolchain packages (...)\" boundary claim found; "
            "state the exact npm coverage in that phrase"
        )
    claimed = match.group(1).strip()
    actual = f"all {len(npm_package_entries(root))} from the lockfile"
    if claimed != actual:
        raise SystemExit(
            f"{COLOPHON}: npm boundary claim {claimed!r} does not match the "
            f"generated coverage {actual!r} - regenerate or correct the prose"
        )


def npm_package_entries(root: Path) -> dict[str, dict]:
    """Every installed package in the lockfile, keyed by its node_modules path.

    The root entry (key "") is the site itself, not a dependency, and is
    excluded — it is the SBOM's metadata component rather than a component.
    """
    document = json.loads(read_text(root, PACKAGE_LOCK))
    if document.get("lockfileVersion") != 3:
        raise SystemExit(
            f"{PACKAGE_LOCK}: this reader speaks lockfileVersion 3, found "
            f"{document.get('lockfileVersion')!r}"
        )
    packages = document.get("packages")
    if not isinstance(packages, dict) or not packages:
        raise SystemExit(f"{PACKAGE_LOCK}: no packages object")
    return {path: entry for path, entry in packages.items() if path}


def npm_name_from_path(path: str) -> str:
    """`node_modules/a/node_modules/@scope/b` -> `@scope/b`."""
    return path.rsplit("node_modules/", 1)[-1]


def npm_purl(name: str, version: str) -> str:
    return f"pkg:npm/{name.replace('@', '%40', 1)}@{version}"


def npm_resolve(entries: dict[str, dict], from_path: str, dep_name: str) -> str | None:
    """The path npm would resolve `dep_name` to from `from_path`.

    npm's rule is nearest-wins: look in the requiring package's own
    node_modules, then each ancestor's, out to the root. Reproducing that is
    what makes the emitted edges the real graph rather than a name-matching
    approximation — a lockfile can legitimately hold two versions of one
    package, and a by-name lookup would attribute both edges to whichever it
    happened to find.
    """
    prefix = from_path
    while True:
        candidate = f"{prefix}/node_modules/{dep_name}"
        if candidate in entries:
            return candidate
        head, sep, _ = prefix.rpartition("/node_modules/")
        if not sep:
            # `node_modules/x` has no "/node_modules/" to partition on, so the
            # walk ends here and the top level is tried explicitly. Folding
            # that into the loop is what made the first version return None for
            # every top-level package's dependencies.
            break
        prefix = head
    top_level = f"node_modules/{dep_name}"
    return top_level if top_level in entries else None


def npm_edge_names(entry: dict) -> list[tuple[str, str]]:
    """Every dependency this package declares, with whether it must resolve.

    WHY three fields and not just `dependencies`: 62 of this lockfile's
    packages are reachable ONLY through `optionalDependencies` or
    `peerDependencies` -- the platform-specific workerd binaries among them.
    Walking `dependencies` alone left those unreachable from any root, so they
    silently took the fallback tier and the SBOM asserted they build the site
    when they in fact belong to the deploy tool. A graph that omits an edge
    kind does not report less, it reports wrong.
    """
    names: list[tuple[str, str]] = []
    for dep_name in sorted(entry.get("dependencies") or {}):
        names.append((dep_name, "required"))
    for field in ("optionalDependencies", "peerDependencies"):
        for dep_name in sorted(entry.get(field) or {}):
            names.append((dep_name, "optional"))
    return names


def npm_tiers(entries: dict[str, dict]) -> dict[str, set[str]]:
    """Which execution tiers each package is reachable in.

    A set rather than a value: a package pulled in by both wrangler and
    playwright genuinely runs at deploy AND at test, and recording one would
    misstate where its code executes.
    """
    tiers: dict[str, set[str]] = {path: set() for path in entries}
    for root_name, tier in NPM_TIER_ROOTS.items():
        start = f"node_modules/{root_name}"
        if start not in entries:
            raise SystemExit(f"{PACKAGE_LOCK}: missing tier root {start}")
        queue = [start]
        seen = {start}
        while queue:
            path = queue.pop()
            tiers[path].add(tier)
            for dep_name, _kind in npm_edge_names(entries[path]):
                resolved = npm_resolve(entries, path, dep_name)
                if resolved and resolved not in seen:
                    seen.add(resolved)
                    queue.append(resolved)
    return tiers


def npm_hashes(entry: dict) -> list[dict]:
    """CycloneDX hashes from the lockfile's Subresource-Integrity string."""
    integrity = entry.get("integrity")
    if not isinstance(integrity, str) or "-" not in integrity:
        return []
    algorithm, _, encoded = integrity.partition("-")
    alg = {"sha512": "SHA-512", "sha256": "SHA-256", "sha1": "SHA-1"}.get(algorithm)
    if alg is None:
        return []
    try:
        content = base64.b64decode(encoded, validate=True).hex()
    except (ValueError, binascii.Error):
        return []
    return [{"alg": alg, "content": content}]


def npm_components(root: Path) -> list[dict]:
    """Every package in the lockfile, with its tier, licence, and integrity."""
    entries = npm_package_entries(root)
    tiers = npm_tiers(entries)
    components = []
    for path, entry in entries.items():
        name = npm_name_from_path(path)
        if not tiers[path]:
            # WHY this is an error rather than a "build" default: every package
            # here was installed because something asked for it, so one that is
            # reachable from no root means NPM_TIER_ROOTS is incomplete. A
            # default would paper over that and publish a tier nobody derived.
            raise SystemExit(
                f"{PACKAGE_LOCK}: {path} is reachable from no entry in "
                "NPM_TIER_ROOTS, so its execution tier cannot be derived; add "
                "the root that pulls it in"
            )
        version = entry.get("version")
        if not isinstance(version, str) or not version:
            raise SystemExit(f"{PACKAGE_LOCK}: {path} has no version")
        license_id = entry.get("license")
        purl = npm_purl(name, version)
        component = {
            "type": "library",
            "bom-ref": path,
            "name": name,
            "version": version,
            "purl": purl,
            "scope": "optional",
            "properties": [
                {"name": "ardent:tier", "value": tier} for tier in sorted(tiers[path])
            ],
        }
        # WHY a property rather than an omission when a licence is absent: the
        # lockfile records no licence for some packages, and silently dropping
        # the field makes an unreviewed licence indistinguishable from one that
        # was checked. Say which it is.
        if isinstance(license_id, str) and license_id:
            component["licenses"] = [license_field(license_id)]
        else:
            component["properties"].append(
                {"name": "ardent:license_status", "value": "absent-from-lockfile"}
            )
        hashes = npm_hashes(entry)
        if hashes:
            component["hashes"] = hashes
        components.append(component)
    components.sort(key=lambda c: c["bom-ref"])
    return components


def npm_dependency_edges(root: Path) -> list[dict]:
    """The CycloneDX dependency graph, resolved the way npm resolves it."""
    entries = npm_package_entries(root)
    edges = []
    for path, entry in sorted(entries.items()):
        depends_on = set()
        for dep_name, kind in npm_edge_names(entry):
            resolved = npm_resolve(entries, path, dep_name)
            if resolved is None:
                if kind == "required":
                    # A required dependency that resolves to nothing is a
                    # lockfile this SBOM cannot describe truthfully, not a row
                    # to quietly omit.
                    raise SystemExit(
                        f"{PACKAGE_LOCK}: {path} requires {dep_name!r}, which "
                        "resolves to no entry in this lockfile"
                    )
                # Optional and peer dependencies legitimately go uninstalled --
                # platform-specific binaries for other operating systems, peers
                # the consumer is expected to supply. An absent one is not an
                # edge in THIS installation, so it is not asserted as one.
                continue
            depends_on.add(resolved)
        edges.append({"ref": path, "dependsOn": sorted(depends_on)})
    return edges


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
    properties = []
    for relative in SBOM_SOURCES:
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
                        "the one runtime-shipped third-party dependency, the pinned "
                        "build toolchain, and every package in package-lock.json "
                        "with the dependency edges npm resolves between them; the "
                        "toolchain itself never ships to a visitor's browser."
                    ),
                },
                *source_provenance(root),
            ],
        },
        "components": components,
        # WHY the graph and not just the list: a list of packages says what is
        # installed; only the edges say what pulls what. A vulnerability in a
        # transitive package is actionable when you can see which direct
        # dependency reaches it, and unactionable otherwise.
        "dependencies": npm_dependency_edges(root),
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
    parser.add_argument(
        "--list-sources",
        action="store_true",
        help="print the SBOM's source-authority paths, one per line, and exit",
    )
    args = parser.parse_args()
    if args.list_sources:
        for relative in SBOM_SOURCES:
            sys.stdout.write(f"{relative.as_posix()}\n")
        return 0
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
