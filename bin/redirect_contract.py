#!/usr/bin/env python3
"""Canonical parsing and probing contract for Cloudflare Pages redirects."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urlparse


REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
SAFE_PATH_RE = re.compile(r"^/[A-Za-z0-9._~!$&'()+,;=:@%*/-]*$")


class RedirectRule(NamedTuple):
    source: str
    target: str
    status: int

    @property
    def declaration(self) -> str:
        return f"{self.source} {self.target} {self.status}"


SUPPORTED_REDIRECTS = (
    RedirectRule("/404", "/404/", 308),
    RedirectRule("/404.html", "/404/", 308),
    RedirectRule("/demos", "/evidence/", 301),
    RedirectRule("/resume", "/consulting/", 301),
    RedirectRule("/systems/ergon-tools/*", "/systems/", 301),
    RedirectRule("/systems/nosologia/*", "/systems/", 301),
    RedirectRule("/demos/*", "/evidence/", 301),
    RedirectRule("/resume/*", "/consulting/", 301),
)
EXACT_PROBE_PATHS = {
    "/demos/*": "/demos/",
    "/resume/*": "/resume/",
}


def source_matches(source: str, path: str) -> bool:
    if source.endswith("*"):
        return path.startswith(source[:-1])
    return path == source


def sources_overlap(left: str, right: str) -> bool:
    if left == right:
        return True
    if left.endswith("*") and right.endswith("*"):
        left_prefix = left[:-1]
        right_prefix = right[:-1]
        return left_prefix.startswith(right_prefix) or right_prefix.startswith(left_prefix)
    if left.endswith("*"):
        return source_matches(left, right)
    if right.endswith("*"):
        return source_matches(right, left)
    return False


def _shape_errors(rule: RedirectRule, label: str, line_number: int) -> list[str]:
    errors: list[str] = []
    context = f"{label}:{line_number}"
    source = rule.source
    target = rule.target
    if (
        not SAFE_PATH_RE.fullmatch(source)
        or not source.startswith("/")
        or source.startswith("//")
        or "\\" in source
        or source.count("*") > 1
        or ("*" in source and not source.endswith("/*"))
    ):
        errors.append(f"{context}: malformed redirect source {source!r}")
    source_parts = urlparse(source)
    if source_parts.query or source_parts.fragment or any(
        segment in {".", ".."} for segment in source_parts.path.split("/")
    ):
        errors.append(f"{context}: malformed redirect source {source!r}")

    target_parts = urlparse(target)
    if (
        not SAFE_PATH_RE.fullmatch(target)
        or not target.startswith("/")
        or target.startswith("//")
        or target_parts.scheme
        or target_parts.netloc
        or target_parts.query
        or target_parts.fragment
        or "\\" in target
        or "*" in target
        or any(segment in {".", ".."} for segment in target_parts.path.split("/"))
    ):
        errors.append(
            f"{context}: redirect target must be one normalized same-origin path; "
            f"found {target!r}"
        )
    if rule.status not in {301, 308}:
        errors.append(
            f"{context}: redirect status must be permanent 301 or 308; "
            f"found {rule.status}"
        )
    if source_matches(source, target):
        errors.append(f"{context}: redirect loops from {source!r} to {target!r}")
    return errors


def parse_redirects(raw: str, label: str = "_redirects") -> tuple[list[RedirectRule], list[str]]:
    """Parse the entire supported declaration set and reject semantic ambiguity."""
    errors: list[str] = []
    rules: list[RedirectRule] = []
    rule_lines: list[int] = []
    for line_number, raw_line in enumerate(raw.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) != 3:
            errors.append(
                f"{label}:{line_number}: malformed redirect declaration; "
                "expected exactly source, target, and status"
            )
            continue
        source, target, status_text = fields
        if not re.fullmatch(r"[0-9]{3}", status_text):
            errors.append(
                f"{label}:{line_number}: malformed redirect status {status_text!r}"
            )
            continue
        rule = RedirectRule(source, target, int(status_text))
        rules.append(rule)
        rule_lines.append(line_number)
        errors.extend(_shape_errors(rule, label, line_number))

    counts = Counter(rules)
    for rule, count in counts.items():
        if count > 1:
            errors.append(
                f"{label}: duplicate redirect declaration {rule.declaration!r} "
                f"appears {count} times"
            )

    source_counts = Counter(rule.source for rule in rules)
    for source, count in source_counts.items():
        if count > 1:
            errors.append(
                f"{label}: duplicate redirect source {source!r} appears {count} times"
            )

    for index, left in enumerate(rules):
        for right in rules[index + 1 :]:
            if left.source != right.source and sources_overlap(left.source, right.source):
                errors.append(
                    f"{label}: ambiguous redirect sources {left.source!r} and "
                    f"{right.source!r} overlap"
                )

    for start in rules:
        visited: set[RedirectRule] = set()
        current = start
        while current not in visited:
            visited.add(current)
            matches = [rule for rule in rules if source_matches(rule.source, current.target)]
            if len(matches) != 1:
                break
            current = matches[0]
        else:
            errors.append(
                f"{label}: redirect cycle is reachable from {start.source!r}"
            )

    supported = set(SUPPORTED_REDIRECTS)
    actual = set(rules)
    for rule in SUPPORTED_REDIRECTS:
        if counts[rule] == 0:
            errors.append(
                f"{label}: missing supported redirect declaration {rule.declaration!r}"
            )
    for rule in sorted(
        actual - supported,
        key=lambda item: (item.source, item.target, item.status),
    ):
        errors.append(
            f"{label}: unsupported extra redirect declaration {rule.declaration!r}"
        )
    return rules, errors


def load_redirects(path: Path) -> tuple[list[RedirectRule], list[str]]:
    try:
        raw = path.read_text()
    except OSError as exc:
        return [], [f"{path}: cannot read redirect declarations: {exc}"]
    return parse_redirects(raw, str(path))


def redirect_probe_path(rule: RedirectRule, expected_revision: str) -> str:
    if not REVISION_RE.fullmatch(expected_revision):
        raise ValueError("expected revision must be exactly one lowercase 40-hex revision")
    if rule.source in EXACT_PROBE_PATHS:
        return EXACT_PROBE_PATHS[rule.source]
    if not rule.source.endswith("*"):
        return rule.source
    material = (
        f"ardent-tools redirect probe\0{expected_revision}\0{rule.source}".encode("ascii")
    )
    token = hashlib.sha256(material).hexdigest()[:24]
    return f"{rule.source[:-1]}__ardent-probe-{token}"
