#!/usr/bin/env python3
"""Unbounded append-only authority for previously published physical assets.

Every entry is a full snapshot of the resources known at that build (not a
diff), so an asset served at commit N but superseded by commit N+10 stays a
retention obligation via the UNION across all entries — that union, not any
single entry, is what `retained-assets/` must physically match. History
grows one entry per asset-touching commit forever by design: CI's
retention-authority step (`bin/asset_retention.py verify`, wired from
deploy.yml) proves the checked-in ledger is an exact, byte-for-byte,
append-only continuation of the event's trusted base revision's ledger —
never edited, never truncated. That is the entire integrity story, and nothing
here weakens it for an ordinary commit.

The one deliberate escape hatch is `compact`: it replaces the full entry
history with one checkpoint entry whose `resources` is the UNION of every
distinct physical resource still retained (so no retention obligation is
lost) and whose `checkpoint_root_sha256` is the canonical digest of the last
entry it replaces. `verify` accepts a checkpoint-rooted transition as an
alternative to literal prefix equality only when TWO independent conditions
both hold (see `validate_history_prefix`'s docstring for the full reasoning):
the root digest matches the trusted base's own last entry — which BINDS the
checkpoint to that exact prior state (prevents a checkpoint minted for an
unrelated ledger from being replayed here; the digest itself is trivially
computable by anyone, since the base ledger is a checked-in public file, so
it proves binding, not authorship) — and the checkpoint's resources are a
superset of the base ledger's own full resource union, re-derived and
checked on the verifying side rather than trusted from the checkpoint's
author. That second check is what actually preserves obligations: a
hand-edited or buggy compaction with a correct root digest but a resources
list silently missing prior obligations fails it explicitly, naming what's
missing. Nothing here erases anything: the squashed per-commit detail
remains fully readable from git history (the deep archive) for anyone
auditing a specific past transition; `compact` only removes the requirement
that every future ledger keep repeating it forever.

Growth is bounded in practice, not by an artificial ceiling: `record_snapshot`
skips writing anything when the current build's resources are unchanged from
the last entry, and `RETENTION_HISTORY_SOFT_WARN_ENTRIES` prints a warning
well before `RETENTION_HISTORY_HARD_LIMIT_ENTRIES` — a defense-in-depth
sanity bound against a corrupted or hostile ledger, not a routine operational
limit — which, if ever actually reached, names the exact remediation
(`python3 bin/asset_retention.py compact`) rather than dead-ending the
repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path, PurePosixPath

from pages_limits import require_static_file_size

LEDGER_SCHEMA_VERSION = 2
RETENTION_HISTORY_SOFT_WARN_ENTRIES = 128
RETENTION_HISTORY_HARD_LIMIT_ENTRIES = 4096
MAX_SNAPSHOT_RESOURCES = 960
MAX_RETAINED_RESOURCES = 960
MAX_RETAINED_BYTES = 256 * 1024 * 1024
ADDRESS_RE = re.compile(r"^a/([0-9a-f]{64})(\.[a-z0-9]+)$")
LOGICAL_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
CHECKPOINT_ROOT_RE = re.compile(r"^[0-9a-f]{64}$")
ENTRY_KINDS = frozenset({"snapshot", "checkpoint"})
SNAPSHOT_ENTRY_KEYS = frozenset(
    {"kind", "sequence", "previous_entry_sha256", "resource_count", "resources"}
)
CHECKPOINT_ENTRY_KEYS = SNAPSHOT_ENTRY_KEYS | {
    "checkpoint_root_sha256",
    "superseded_entry_count",
}
COMPACT_COMMAND = (
    "python3 bin/asset_retention.py compact "
    "--ledger asset-retention.json --assets retained-assets"
)
MISSING_OBLIGATION_SAMPLE = 5


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
    if not isinstance(entries, list) or len(entries) < 1:
        raise ValueError("asset retention entries must contain at least 1 snapshot")
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
        kind = entry.get("kind") if isinstance(entry, dict) else None
        if kind not in ENTRY_KINDS:
            raise ValueError(f"{label} kind must be one of {sorted(ENTRY_KINDS)}")
        is_checkpoint = kind == "checkpoint"
        expected_keys = CHECKPOINT_ENTRY_KEYS if is_checkpoint else SNAPSHOT_ENTRY_KEYS
        if set(entry) != expected_keys:
            raise ValueError(f"{label} has unexpected or missing keys")
        if is_checkpoint and index != 0:
            raise ValueError(f"{label} checkpoint entries must be the ledger's first entry")
        if is_checkpoint:
            root = entry.get("checkpoint_root_sha256")
            if not isinstance(root, str) or not CHECKPOINT_ROOT_RE.fullmatch(root):
                raise ValueError(f"{label} checkpoint_root_sha256 must be a 64-hex digest")
            superseded = entry.get("superseded_entry_count")
            if (
                not isinstance(superseded, int)
                or isinstance(superseded, bool)
                or superseded < 2
            ):
                raise ValueError(
                    f"{label} superseded_entry_count must be an integer of at least 2"
                )
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
    if len(entries) >= RETENTION_HISTORY_HARD_LIMIT_ENTRIES:
        raise ValueError(
            f"asset retention ledger holds {len(entries)} entries, at its "
            f"{RETENTION_HISTORY_HARD_LIMIT_ENTRIES}-entry safety ceiling; run "
            f"`{COMPACT_COMMAND}` to squash history into one checkpoint entry "
            "before recording another snapshot"
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
        "kind": "snapshot",
        "sequence": len(entries) + 1,
        "previous_entry_sha256": previous,
        "resource_count": len(snapshot),
        "resources": snapshot,
    }
    entries.append(entry)
    document["entry_count"] = len(entries)
    write_atomic(ledger_path, serialize_ledger(document))
    validate_ledger(ledger_path, asset_root)
    if len(entries) >= RETENTION_HISTORY_SOFT_WARN_ENTRIES:
        sys.stderr.write(
            f"WARNING: asset retention ledger holds {len(entries)} entries "
            f"(soft threshold {RETENTION_HISTORY_SOFT_WARN_ENTRIES}, hard "
            f"safety ceiling {RETENTION_HISTORY_HARD_LIMIT_ENTRIES}); "
            f"consider `{COMPACT_COMMAND}` before it grows much further\n"
        )
    return document


def resource_union(entries: list) -> dict[str, str]:
    """Union of retained (output_path -> sha256) obligations across entries.

    Matches the semantics record_checkpoint() uses to compute a checkpoint's
    own resources: every physical resource any entry's resources list ever
    named stays a retention obligation regardless of which entry currently
    reflects it as "current". Tolerant of malformed items (skips rather than
    raises) since callers use this on ledgers that may not have independently
    passed validate_ledger() yet — a defensive best-effort union, not itself
    a source of structural validation.
    """
    union: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        resources = entry.get("resources")
        if not isinstance(resources, list):
            continue
        for item in resources:
            if not isinstance(item, dict):
                continue
            output = item.get("output_path")
            digest = item.get("sha256")
            if isinstance(output, str) and isinstance(digest, str):
                union[output] = digest
    return union


def record_checkpoint(ledger_path: Path, asset_root: Path) -> dict:
    """Squash the full current ledger history into one checkpoint entry.

    The checkpoint's `resources` is the UNION of every distinct physical
    output_path currently retained (re-derived here from `validate_ledger`'s
    own retained-assets membership proof, not merely copied from the latest
    entry — an entry only records ONE build's finalized map, so an
    output_path served by an earlier, already-superseded build would
    otherwise silently drop out of the retention obligation). Because a
    physical output_path already carries its own content hash, the union is
    naturally unique per output_path regardless of how many different
    logical_path names pointed at it historically; each item's logical_path
    here is synthesized (`checkpoint/<sha256><ext>`) rather than copied from
    any one historical record, since no single one is more canonical than
    the others and the physical identity is what retention actually
    guarantees.
    """
    document, bodies = validate_ledger(ledger_path, asset_root)
    entries = document["entries"]
    if len(entries) <= 1:
        raise ValueError(
            "asset retention ledger already holds at most one entry; nothing to compact"
        )
    resources = snapshot_resources(
        [
            {
                "logical_path": f"checkpoint/{sha256_bytes(body)}{PurePosixPath(output).suffix}",
                "output_path": output,
                "sha256": sha256_bytes(body),
            }
            for output, body in bodies.items()
        ]
    )
    checkpoint = {
        "kind": "checkpoint",
        "sequence": 1,
        "previous_entry_sha256": None,
        "resource_count": len(resources),
        "resources": resources,
        "checkpoint_root_sha256": entry_digest(entries[-1]),
        "superseded_entry_count": len(entries),
    }
    compacted = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "entry_count": 1,
        "entries": [checkpoint],
    }
    write_atomic(ledger_path, serialize_ledger(compacted))
    validate_ledger(ledger_path, asset_root)
    return compacted


def validate_history_prefix(current: dict, prior_path: Path) -> None:
    """Bind the checked-in ledger to an independently selected prior revision.

    Ordinarily this requires literal equality: current's entries must begin
    with every entry prior's did, in the same order — an append-only,
    never-edited history. The sole exception is a compaction commit, and it
    is checked in two independent parts, because neither alone is sufficient:

    1. checkpoint_root_sha256 must equal the canonical digest of prior's own
       last entry. Prior is a checked-in file, so this digest is trivially
       *computable* by anyone — it proves nothing about what produced the
       checkpoint. What it proves is BINDING: this checkpoint claims to
       summarize exactly prior's history and no other, so it cannot be a
       checkpoint minted for an unrelated ledger and replayed here.
    2. The checkpoint's resources must be a SUPERSET of resource_union(prior
       entries) — every (output_path, sha256) obligation prior's full history
       held must still appear in the checkpoint, identically. This is the
       actual obligation-preservation proof: without it, a hand-edited or
       buggy compaction could carry a correct root digest while silently
       dropping resources record_checkpoint()'s real union would have kept
       (and validate_ledger() alone cannot catch this, since it only proves
       the entries it's GIVEN are internally consistent with what's on disk —
       it has no notion of what an earlier, now-replaced ledger required).
       Superset, not equality: a local ledger legitimately ahead of the base
       before compacting carries more current resources than the base ever
       named.
    """
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
    checkpoint = current_entries[0] if current_entries else None
    if (
        prior_entries
        and isinstance(checkpoint, dict)
        and checkpoint.get("kind") == "checkpoint"
        and checkpoint.get("checkpoint_root_sha256") == entry_digest(prior_entries[-1])
    ):
        prior_obligations = resource_union(prior_entries)
        checkpoint_obligations = resource_union([checkpoint])
        missing = sorted(
            output
            for output, digest in prior_obligations.items()
            if checkpoint_obligations.get(output) != digest
        )
        if missing:
            sample = ", ".join(missing[:MISSING_OBLIGATION_SAMPLE])
            remainder = len(missing) - MISSING_OBLIGATION_SAMPLE
            if remainder > 0:
                sample += f" (+{remainder} more)"
            raise ValueError(
                "asset-retention checkpoint drops retention obligations the "
                f"base ledger held: {sample}"
            )
        return
    if len(current_entries) < len(prior_entries):
        raise ValueError("asset-retention history was truncated relative to the base")
    if current_entries[: len(prior_entries)] != prior_entries:
        raise ValueError(
            "asset-retention history is not an exact append-only base prefix"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    verify_parser = subparsers.add_parser(
        "verify", help="prove the current ledger extends the trusted base ledger"
    )
    verify_parser.add_argument(
        "--ledger", type=Path, default=Path("asset-retention.json")
    )
    verify_parser.add_argument(
        "--assets", type=Path, default=Path("retained-assets")
    )
    verify_parser.add_argument("--prior-ledger", type=Path, required=True)

    compact_parser = subparsers.add_parser(
        "compact", help="squash ledger history into one checkpoint entry"
    )
    compact_parser.add_argument(
        "--ledger", type=Path, default=Path("asset-retention.json")
    )
    compact_parser.add_argument(
        "--assets", type=Path, default=Path("retained-assets")
    )

    args = parser.parse_args()
    try:
        if args.command == "verify":
            current, _bodies = validate_ledger(args.ledger, args.assets)
            validate_history_prefix(current, args.prior_ledger)
            print(
                "PASS: asset-retention ledger preserves the independently "
                "selected base prefix"
            )
            return 0
        document = record_checkpoint(args.ledger, args.assets)
        checkpoint = document["entries"][0]
        print(
            "PASS: asset-retention ledger compacted "
            f"{checkpoint['superseded_entry_count']} entries into one "
            f"checkpoint covering {checkpoint['resource_count']} retained "
            "resources"
        )
        return 0
    except ValueError as exc:
        parser.error(str(exc))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
