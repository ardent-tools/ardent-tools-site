#!/usr/bin/env python3
"""Bounded append-only authority for previously published physical assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import tempfile
from pathlib import Path, PurePosixPath

from pages_limits import require_static_file_size

LEDGER_SCHEMA_VERSION = 1
MAX_ENTRIES = 128
MAX_SNAPSHOT_RESOURCES = 960
MAX_RETAINED_RESOURCES = 960
MAX_RETAINED_BYTES = 256 * 1024 * 1024
ADDRESS_RE = re.compile(r"^a/([0-9a-f]{64})(\.[a-z0-9]+)$")
LOGICAL_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def strict_json(raw: str, label: str) -> object:
    def reject_constant(value: str) -> None:
        raise ValueError(f"{label}: non-finite JSON constant {value!r}")

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict:
        result: dict = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"{label}: duplicate key {key!r}")
            result[key] = value
        return result

    try:
        return json.loads(
            raw,
            parse_constant=reject_constant,
            object_pairs_hook=reject_duplicates,
        )
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise ValueError(f"{label}: not strict JSON: {exc}") from exc


def valid_logical_path(value: object) -> bool:
    if (
        not isinstance(value, str)
        or not value
        or value.startswith(("/", ".", "a/"))
        or not LOGICAL_RE.fullmatch(value)
        or "//" in value
        or "\\" in value
    ):
        return False
    return all(part not in {"", ".", ".."} for part in PurePosixPath(value).parts)


def entry_digest(entry: dict) -> str:
    canonical = json.dumps(
        entry, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("ascii")
    return sha256_bytes(canonical)


def serialize_ledger(document: dict) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_atomic(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def snapshot_resources(resources: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(
        [
            {
                "logical_path": item["logical_path"],
                "output_path": item["output_path"],
                "sha256": item["sha256"],
            }
            for item in resources
        ],
        key=lambda item: item["logical_path"],
    )


def validate_ledger(
    ledger_path: Path, asset_root: Path
) -> tuple[dict, dict[str, bytes]]:
    try:
        ledger_metadata = ledger_path.lstat()
        asset_metadata = asset_root.lstat()
    except OSError as exc:
        raise ValueError(f"asset retention authority is unavailable: {exc}") from exc
    if stat.S_ISLNK(ledger_metadata.st_mode) or not stat.S_ISREG(
        ledger_metadata.st_mode
    ):
        raise ValueError("asset retention ledger must be one regular non-symlink file")
    if stat.S_ISLNK(asset_metadata.st_mode) or not stat.S_ISDIR(asset_metadata.st_mode):
        raise ValueError("retained asset root must be one real directory")
    try:
        raw = ledger_path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"asset retention ledger is not strict UTF-8: {exc}") from exc
    document = strict_json(raw, "asset retention ledger")
    if not isinstance(document, dict) or set(document) != {
        "schema_version",
        "entry_count",
        "entries",
    }:
        raise ValueError("asset retention ledger has unexpected or missing keys")
    if (
        not isinstance(document.get("schema_version"), int)
        or isinstance(document.get("schema_version"), bool)
        or document["schema_version"] != LEDGER_SCHEMA_VERSION
    ):
        raise ValueError(
            f"asset retention schema_version must be {LEDGER_SCHEMA_VERSION}"
        )
    entries = document.get("entries")
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_ENTRIES:
        raise ValueError(
            f"asset retention entries must contain 1..{MAX_ENTRIES} snapshots"
        )
    if (
        not isinstance(document.get("entry_count"), int)
        or isinstance(document.get("entry_count"), bool)
        or document["entry_count"] != len(entries)
    ):
        raise ValueError("asset retention entry_count differs from entries length")

    retained: dict[str, str] = {}
    previous_digest: str | None = None
    for index, entry in enumerate(entries):
        label = f"asset retention entries[{index}]"
        if not isinstance(entry, dict) or set(entry) != {
            "sequence",
            "previous_entry_sha256",
            "resource_count",
            "resources",
        }:
            raise ValueError(f"{label} has unexpected or missing keys")
        if (
            not isinstance(entry.get("sequence"), int)
            or isinstance(entry.get("sequence"), bool)
            or entry["sequence"] != index + 1
        ):
            raise ValueError(f"{label} sequence must be {index + 1}")
        if entry.get("previous_entry_sha256") != previous_digest:
            raise ValueError(f"{label} does not preserve the append-only hash chain")
        resources = entry.get("resources")
        if (
            not isinstance(resources, list)
            or not 1 <= len(resources) <= MAX_SNAPSHOT_RESOURCES
        ):
            raise ValueError(
                f"{label} resources must contain 1..{MAX_SNAPSHOT_RESOURCES} members"
            )
        if (
            not isinstance(entry.get("resource_count"), int)
            or isinstance(entry.get("resource_count"), bool)
            or entry["resource_count"] != len(resources)
        ):
            raise ValueError(f"{label} resource_count differs from resources length")
        if resources != sorted(
            resources,
            key=lambda item: (
                item.get("logical_path", "") if isinstance(item, dict) else ""
            ),
        ):
            raise ValueError(f"{label} resources must be sorted by logical_path")
        seen_logical: set[str] = set()
        for resource_index, item in enumerate(resources):
            item_label = f"{label}.resources[{resource_index}]"
            if not isinstance(item, dict) or set(item) != {
                "logical_path",
                "output_path",
                "sha256",
            }:
                raise ValueError(f"{item_label} has unexpected or missing keys")
            logical = item.get("logical_path")
            output = item.get("output_path")
            digest = item.get("sha256")
            if not valid_logical_path(logical):
                raise ValueError(f"{item_label} has invalid logical_path {logical!r}")
            if logical in seen_logical:
                raise ValueError(f"{label} repeats logical_path {logical!r}")
            seen_logical.add(logical)
            match = ADDRESS_RE.fullmatch(output) if isinstance(output, str) else None
            if match is None or match.group(1) != digest:
                raise ValueError(
                    f"{item_label} output_path must carry its exact full SHA-256"
                )
            if PurePosixPath(logical).suffix.lower() != match.group(2):
                raise ValueError(
                    f"{item_label} physical extension differs from logical_path"
                )
            prior = retained.get(output)
            if prior is not None and prior != digest:
                raise ValueError(
                    f"{item_label} conflicts with an earlier physical path"
                )
            retained[output] = digest
        previous_digest = entry_digest(entry)

    if len(retained) > MAX_RETAINED_RESOURCES:
        raise ValueError(
            f"asset retention contains more than {MAX_RETAINED_RESOURCES} physical resources"
        )
    files: dict[str, Path] = {}
    for path in sorted(asset_root.rglob("*")):
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(
                f"retained asset must not be a symlink: {path.relative_to(asset_root)}"
            )
        if not stat.S_ISREG(metadata.st_mode):
            continue
        relative = path.relative_to(asset_root).as_posix()
        if ADDRESS_RE.fullmatch(relative) is None:
            raise ValueError(f"retained asset has invalid physical path: {relative}")
        files[relative] = path
    if set(files) != set(retained):
        raise ValueError(
            "retained asset files differ from ledger; "
            f"missing={sorted(set(retained) - set(files))}, "
            f"extra={sorted(set(files) - set(retained))}"
        )
    bodies: dict[str, bytes] = {}
    total_bytes = 0
    for output, path in files.items():
        require_static_file_size(path.stat().st_size, f"retained asset {output}")
        body = path.read_bytes()
        total_bytes += len(body)
        if sha256_bytes(body) != retained[output]:
            raise ValueError(
                f"retained asset body differs from filename digest: {output}"
            )
        bodies[output] = body
    if total_bytes > MAX_RETAINED_BYTES:
        raise ValueError(
            f"retained assets exceed bounded {MAX_RETAINED_BYTES}-byte authority"
        )
    return document, bodies


def record_snapshot(
    ledger_path: Path,
    asset_root: Path,
    resources: list[dict[str, str]],
    bodies: dict[str, bytes],
) -> dict:
    snapshot = snapshot_resources(resources)
    if not snapshot:
        raise ValueError("cannot record an empty asset-retention snapshot")
    if ledger_path.exists() or asset_root.exists():
        document, _retained = validate_ledger(ledger_path, asset_root)
    else:
        document = {
            "schema_version": LEDGER_SCHEMA_VERSION,
            "entry_count": 0,
            "entries": [],
        }
        asset_root.mkdir(parents=True)
    entries = document["entries"]
    if entries and entries[-1]["resources"] == snapshot:
        return document
    if len(entries) >= MAX_ENTRIES:
        raise ValueError(
            f"asset retention reached its bounded {MAX_ENTRIES}-snapshot limit"
        )
    for item in snapshot:
        output = item["output_path"]
        body = bodies.get(output)
        if body is None or sha256_bytes(body) != item["sha256"]:
            raise ValueError(
                f"current physical body is unavailable for retention: {output}"
            )
        require_static_file_size(len(body), f"current physical asset {output}")
        destination = asset_root / output
        if destination.exists():
            if not destination.is_file() or destination.is_symlink():
                raise ValueError(f"retained asset destination is not regular: {output}")
            if destination.read_bytes() != body:
                raise ValueError(f"retained asset collision: {output}")
        else:
            write_atomic(destination, body)
    previous = entry_digest(entries[-1]) if entries else None
    entry = {
        "sequence": len(entries) + 1,
        "previous_entry_sha256": previous,
        "resource_count": len(snapshot),
        "resources": snapshot,
    }
    entries.append(entry)
    document["entry_count"] = len(entries)
    write_atomic(ledger_path, serialize_ledger(document))
    validate_ledger(ledger_path, asset_root)
    return document


def validate_history_prefix(current: dict, prior_path: Path) -> None:
    """Bind the checked-in ledger to an independently selected prior revision."""
    try:
        prior_raw = prior_path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"prior asset-retention ledger is unavailable: {exc}") from exc
    prior = strict_json(prior_raw, "prior asset-retention ledger")
    if not isinstance(prior, dict) or set(prior) != {
        "schema_version",
        "entry_count",
        "entries",
    }:
        raise ValueError("prior asset-retention ledger has an invalid shape")
    prior_entries = prior.get("entries")
    if (
        not isinstance(prior.get("schema_version"), int)
        or isinstance(prior.get("schema_version"), bool)
        or prior.get("schema_version") != LEDGER_SCHEMA_VERSION
        or not isinstance(prior_entries, list)
        or not isinstance(prior.get("entry_count"), int)
        or isinstance(prior.get("entry_count"), bool)
        or prior.get("entry_count") != len(prior_entries)
    ):
        raise ValueError("prior asset-retention ledger metadata is invalid")
    current_entries = current["entries"]
    if len(current_entries) < len(prior_entries):
        raise ValueError("asset-retention history was truncated relative to the base")
    if current_entries[: len(prior_entries)] != prior_entries:
        raise ValueError(
            "asset-retention history is not an exact append-only base prefix"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, default=Path("asset-retention.json"))
    parser.add_argument("--assets", type=Path, default=Path("retained-assets"))
    parser.add_argument("--prior-ledger", type=Path, required=True)
    args = parser.parse_args()
    try:
        current, _bodies = validate_ledger(args.ledger, args.assets)
        validate_history_prefix(current, args.prior_ledger)
    except ValueError as exc:
        parser.error(str(exc))
    print(
        "PASS: asset-retention ledger preserves the independently selected base prefix"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
