#!/usr/bin/env python3
"""Canonical build, derivation, authoring, and gate entrypoint for this site."""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DERIVATIONS = (
    ("bin/generate-systems-json.py", "static/systems.json"),
    ("bin/validate-career-claims.py", "static/career-claims.json"),
)
USAGE = (
    "usage: python3 bin/site.py "
    "{sync|verify|check|build|serve|gate|retain-assets} [zola args]"
)
STABLE_SYNC_ATTEMPTS = 3


class UnstableDerivationInputs(RuntimeError):
    """Authority inputs kept changing while a coherent derivation was attempted."""


def run(command: list[str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


def verify_derivations() -> None:
    for script, output in DERIVATIONS:
        run([sys.executable, script, "--output", output, "--check"])


def verify_writing_tiers() -> None:
    # WHY: the two-tier /writing/ template groups by extra.tier; an untagged
    # entry would fall through both groups and vanish from the listing. Fail
    # closed on any writing entry missing a valid tier.
    valid = {"notes", "research"}
    problems: list[str] = []
    for path in sorted((ROOT / "content/writing").glob("*.md")):
        if path.name == "_index.md":
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        fences = [i for i, line in enumerate(lines) if line.strip() == "+++"]
        tier = None
        if len(fences) >= 2:
            frontmatter = "\n".join(lines[fences[0] + 1 : fences[1]])
            tier = tomllib.loads(frontmatter).get("extra", {}).get("tier")
        if tier not in valid:
            problems.append(
                f"{path.relative_to(ROOT)}: extra.tier must be one of "
                f"{sorted(valid)}, got {tier!r}"
            )
    if problems:
        sys.stderr.write(
            "ERROR: writing entries missing a valid extra.tier:\n  "
            + "\n  ".join(problems)
            + "\n"
        )
        raise SystemExit(1)


def atomic_write(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fchmod(handle.fileno(), 0o644)
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def sync_derivations() -> None:
    with tempfile.TemporaryDirectory(prefix="ardent-site-derive.") as directory:
        temporary_root = Path(directory)
        rendered: list[tuple[Path, bytes]] = []
        for index, (script, output) in enumerate(DERIVATIONS):
            temporary = temporary_root / f"derived-{index}.json"
            run([sys.executable, script, "--output", str(temporary)])
            rendered.append((ROOT / output, temporary.read_bytes()))
        for target, body in rendered:
            if (
                target.is_file()
                and target.read_bytes() == body
                and target.stat().st_mode & 0o777 == 0o644
            ):
                continue
            atomic_write(target, body)
    verify_derivations()


def derivation_inputs() -> list[Path]:
    inputs = [
        ROOT / "data/career-claims.json",
        ROOT / "data/exact-system-licenses.json",
        ROOT / "content/about.md",
        ROOT / "resume/cody-kickertz-resume.typ",
        ROOT / "static/files/cody-kickertz-resume.pdf",
    ]
    inputs.extend(sorted((ROOT / "content/systems").glob("*.md")))
    return inputs


def input_fingerprint() -> str:
    digest = hashlib.sha256()
    for path in derivation_inputs():
        relative = path.relative_to(ROOT).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        try:
            metadata = path.lstat()
            file_type = stat.S_IFMT(metadata.st_mode)
            digest.update(f"TYPE:{file_type:o}".encode("ascii"))
            digest.update(b"\0")
            if stat.S_ISLNK(metadata.st_mode):
                digest.update(f"TARGET:{os.readlink(path)}".encode("utf-8"))
                digest.update(b"\0")
                continue
            if not stat.S_ISREG(metadata.st_mode):
                continue
            digest.update(path.read_bytes())
        except OSError as exc:
            digest.update(f"ERROR:{exc}".encode("utf-8", errors="replace"))
        digest.update(b"\0")
    return digest.hexdigest()


def sync_stable() -> str:
    for _attempt in range(STABLE_SYNC_ATTEMPTS):
        before = input_fingerprint()
        sync_derivations()
        after = input_fingerprint()
        if before == after:
            return after
    raise UnstableDerivationInputs(
        f"authority inputs changed during {STABLE_SYNC_ATTEMPTS} consecutive derivations"
    )


def terminate_child(child: subprocess.Popen) -> int:
    if child.poll() is not None:
        return child.returncode
    child.terminate()
    try:
        return child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        child.kill()
        return child.wait()


def serve(arguments: list[str]) -> int:
    observed = sync_stable()
    child = subprocess.Popen(["zola", "serve", *arguments], cwd=ROOT)
    try:
        while child.poll() is None:
            current = input_fingerprint()
            if current != observed:
                try:
                    observed = sync_stable()
                except (
                    OSError,
                    subprocess.CalledProcessError,
                    UnstableDerivationInputs,
                ) as exc:
                    detail = (
                        f"exit {exc.returncode}"
                        if isinstance(exc, subprocess.CalledProcessError)
                        else str(exc)
                    )
                    sys.stderr.write(
                        "ERROR: derivation refresh failed after source change "
                        f"({detail}); stopping the authoring server\n"
                    )
                    return (
                        exc.returncode
                        if isinstance(exc, subprocess.CalledProcessError)
                        and exc.returncode > 0
                        else 1
                    )
            time.sleep(0.35)
        return child.returncode
    except KeyboardInterrupt:
        return terminate_child(child)
    except OSError as exc:
        sys.stderr.write(
            f"ERROR: cannot inspect derivation inputs ({exc}); "
            "stopping the authoring server\n"
        )
        return 1
    finally:
        if child.poll() is None:
            terminate_child(child)


def retain_assets() -> None:
    """Explicitly append the current finalized public assets to retention."""
    verify_derivations()
    with tempfile.TemporaryDirectory(prefix="ardent-retain-assets.") as directory:
        temporary_root = Path(directory)
        output = temporary_root / "public"
        asset_map = temporary_root / "asset-map.json"
        run(["zola", "build", "--output-dir", str(output)])
        shutil.copyfile(ROOT / "_headers", output / "_headers")
        shutil.copyfile(ROOT / "_redirects", output / "_redirects")
        for relative in ("casts/.gitkeep", "css/.gitkeep", "js/.gitkeep"):
            placeholder = output / relative
            if placeholder.is_file() and not placeholder.is_symlink():
                placeholder.unlink()
        (output / "build-revision.txt").write_text("0" * 40 + "\n")
        run(
            [
                sys.executable,
                "bin/content_address.py",
                str(output),
                "--map",
                str(asset_map),
                "--base-url",
                "https://ardent.tools",
                "--record-retention-snapshot",
            ]
        )
    sys.stdout.write(
        "PASS: current physical assets recorded; run the strict gate before commit\n"
    )


def main() -> int:
    os.chdir(ROOT)
    if len(sys.argv) < 2 or sys.argv[1] in {"-h", "--help"}:
        stream = sys.stdout if len(sys.argv) >= 2 else sys.stderr
        stream.write(f"{USAGE}\n")
        return 0 if len(sys.argv) >= 2 else 2
    command = sys.argv[1]
    arguments = sys.argv[2:]
    if arguments[:1] == ["--"]:
        arguments = arguments[1:]
    if command in {"sync", "verify", "gate", "retain-assets"} and arguments:
        sys.stderr.write(f"ERROR: {command} accepts no additional arguments\n{USAGE}\n")
        return 2
    try:
        if command == "sync":
            sync_stable()
            return 0
        if command == "verify":
            verify_derivations()
            return 0
        if command in {"check", "build"}:
            verify_writing_tiers()
            verify_derivations()
            os.execvp("zola", ["zola", command, *arguments])
        if command == "serve":
            return serve(arguments)
        if command == "gate":
            os.execvp("bash", ["bash", "bin/check-site.sh"])
        if command == "retain-assets":
            retain_assets()
            return 0
    except subprocess.CalledProcessError as exc:
        return exc.returncode
    except FileNotFoundError as exc:
        sys.stderr.write(f"ERROR: required executable is missing: {exc.filename}\n")
        return 1
    sys.stderr.write(f"ERROR: unknown command {command!r}\n{USAGE}\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
