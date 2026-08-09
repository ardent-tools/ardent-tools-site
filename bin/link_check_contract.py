#!/usr/bin/env python3
"""Fail-closed classifier for a lychee external-link JSON report.

Consumes lychee's own `--format json` report (never its human-readable
text) and permits exactly one narrow, explicit transient set to degrade a
survived retry into a warning: a reachable host answering with a 5xx, or
a genuine request timeout. Everything else - a rejected status outside
5xx (including every 4xx dead link), a connection-level failure (DNS,
TLS, refused - lychee reports none of these with a status code, so they
cannot be told apart from "our own network broke"), a missing/unreadable
report, or a report whose shape lychee has changed - fails closed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEGRADABLE_STATUS_MIN = 500
DEGRADABLE_STATUS_MAX = 599
REQUIRED_REPORT_KEYS = ("error_map", "timeout_map")


class LinkCheckReportError(ValueError):
    """The lychee report is missing, unparsable, or structurally unexpected."""


def parse_report(raw: bytes) -> dict:
    try:
        report = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LinkCheckReportError(f"lychee report is not valid JSON: {exc}") from exc
    if not isinstance(report, dict):
        raise LinkCheckReportError("lychee report top level must be a JSON object")
    for key in REQUIRED_REPORT_KEYS:
        if key not in report or not isinstance(report[key], dict):
            raise LinkCheckReportError(f"lychee report is missing expected key {key!r}")
    return report


def classify(report: dict) -> tuple[list[dict], list[dict]]:
    """Split lychee's survivors into (hard_failures, degraded)."""
    hard_failures: list[dict] = []
    degraded: list[dict] = []
    for source, entries in report["error_map"].items():
        for entry in entries:
            status = entry.get("status", {}) if isinstance(entry, dict) else {}
            code = status.get("code") if isinstance(status, dict) else None
            record = {
                "source": source,
                "url": entry.get("url", "<unknown>") if isinstance(entry, dict) else "<unknown>",
                "status_code": code,
                "detail": (status.get("text") or status.get("details") or "")
                if isinstance(status, dict)
                else "",
            }
            if isinstance(code, int) and DEGRADABLE_STATUS_MIN <= code <= DEGRADABLE_STATUS_MAX:
                degraded.append({**record, "reason": "server-5xx"})
            else:
                hard_failures.append(record)
    for source, entries in report["timeout_map"].items():
        for entry in entries:
            status = entry.get("status", {}) if isinstance(entry, dict) else {}
            degraded.append(
                {
                    "source": source,
                    "url": entry.get("url", "<unknown>") if isinstance(entry, dict) else "<unknown>",
                    "status_code": None,
                    "detail": status.get("details") or "" if isinstance(status, dict) else "",
                    "reason": "timeout",
                }
            )
    return hard_failures, degraded


def render_receipt(degraded: list[dict]) -> dict:
    """A machine-readable record of exactly what was let through, and why."""
    return {"degraded_count": len(degraded), "findings": degraded}


def run(report_path: Path, receipt_path: Path | None, stdout, stderr) -> int:
    try:
        raw = report_path.read_bytes()
    except OSError as exc:
        stderr.write(f"ERROR: lychee report is missing or unreadable: {exc}\n")
        return 1
    try:
        report = parse_report(raw)
    except LinkCheckReportError as exc:
        stderr.write(f"ERROR: {exc}\n")
        return 1

    hard_failures, degraded = classify(report)
    if hard_failures:
        for failure in hard_failures:
            code = failure["status_code"]
            label = f"[{code}]" if code is not None else "[connection]"
            line = f"ERROR: {failure['url']} {label} {failure['detail']}".rstrip()
            stderr.write(f"{line}\n")
        stderr.write(
            f"ERROR: {len(hard_failures)} external link check failure(s) survived retry "
            "and are outside the permitted transient set (5xx, timeout)\n"
        )
        return 1

    receipt = render_receipt(degraded)
    if receipt_path is not None:
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    for finding in degraded:
        line = (
            "WARNING: degraded (upstream unavailability, not link rot): "
            f"{finding['url']} ({finding['reason']}) {finding['detail']}"
        ).rstrip()
        stderr.write(f"{line}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="lychee --format json report path")
    parser.add_argument(
        "--receipt", type=Path, default=None, help="write the degraded receipt JSON here"
    )
    args = parser.parse_args(argv)
    return run(args.report, args.receipt, sys.stdout, sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
