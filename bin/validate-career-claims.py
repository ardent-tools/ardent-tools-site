#!/usr/bin/env python3
"""Validate typed career claims and derive their public verification receipt."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

from career_claim_contract import FORBIDDEN_PUBLIC_VARIANTS


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY_PATH = Path("data/career-claims.json")
RECEIPT_PATH = Path("static/career-claims.json")
PDF_PATH = Path("static/files/cody-kickertz-resume.pdf")
SCHEMA_VERSION = 2
RECEIPT_SCHEMA_VERSION = 2
CLAIM_ID = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)+$")
VALUE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
SURFACE_PATHS = {
    "about": "content/about.md",
    "resume_source": "resume/cody-kickertz-resume.typ",
    "resume_pdf": PDF_PATH.as_posix(),
}
TOP_LEVEL_KEYS = {
    "schema_version",
    "verification_scope",
    "evidence_boundary",
    "evidence_authorities",
    "excluded_public_claims",
    "claims",
}
CLAIM_KEYS = {
    "id",
    "scope",
    "evidence_ref",
    "provenance",
    "verified_at",
    "valid_through",
    "values",
    "renderings",
}
EVIDENCE_AUTHORITY_KEYS = {
    "id",
    "kind",
    "custodian",
    "access",
    "review_basis",
    "recorded_at",
    "source_locator",
    "source_sha256",
    "underlying_private_evidence_inspected",
}
PROVENANCE_KEYS = {"kind", "recorded_at", "authority_sha256"}
AUTHORITY_ID = "operator-authorization:ardent-evidence-lab-truth-release"
AUTHORITY_SOURCE_SHA256 = (
    "3f67adad273d478993571b1fc2a71fc67fad7b197844db5f36ad2bcf6947304c"
)
EXPECTED_VERIFICATION_SCOPE = ["about", "resume_source", "resume_pdf"]
EXPECTED_EVIDENCE_BOUNDARY = {
    "underlying_private_evidence_inspected": False,
    "underlying_private_evidence_published": False,
}
EXPECTED_EVIDENCE_AUTHORITY = {
    "id": AUTHORITY_ID,
    "kind": "operator_authorization",
    "custodian": "site_operator",
    "access": "private",
    "review_basis": "operator_truth_release",
    "recorded_at": "2026-07-22",
    "source_locator": "fleet-dispatch:ardent-evidence-lab-truth-release",
    "source_sha256": AUTHORITY_SOURCE_SHA256,
    "underlying_private_evidence_inspected": False,
}
EXPECTED_EXCLUDED_PUBLIC_CLAIMS = [
    {"topic": "disbursing-office_rank", "decision": "not_asserted"},
    {"topic": "deployment_nation_count", "decision": "not_asserted"},
]
EXPECTED_PROVENANCE = {
    "kind": "operator_authorized_public_subset",
    "recorded_at": "2026-07-22",
    "authority_sha256": AUTHORITY_SOURCE_SHA256,
}
EXPECTED_CLAIMS = {
    "usmc.disbursing-office.people-and-functions": {
        "scope": "camp_lejeune_disbursing_office_role",
        "values": {
            "marines": {"value": 157, "unit": "people", "display": "157 Marines"},
            "civilians": {"value": 12, "unit": "people", "display": "12 civilians"},
            "finance_functions": {
                "value": 7,
                "unit": "functions",
                "display": "seven finance functions",
            },
        },
        "renderings": {
            "about": (
                "helping lead a disbursing office of 157 Marines and 12 civilians "
                "across seven finance functions"
            ),
            "resume_source": (
                "Helped lead a disbursing office of 157 Marines and 12 civilians "
                "across seven finance functions."
            ),
            "resume_pdf": (
                "Helped lead a disbursing office of 157 Marines and 12 civilians "
                "across seven finance functions."
            ),
        },
    },
    "usmc.meu.deployment": {
        "scope": "twenty_second_meu_deployment",
        "values": {
            "duration": {"value": 7, "unit": "months", "display": "seven-month"},
            "naval_vessels": {
                "value": 3,
                "unit": "vessels",
                "display": "three naval vessels",
            },
            "meu_population": {
                "value": 3_000,
                "unit": "people",
                "display": "3,000-person",
            },
        },
        "renderings": {
            "about": (
                "seven-month deployment aboard three naval vessels supporting a "
                "3,000-person Marine Expeditionary Unit"
            ),
            "resume_source": (
                "Ran fiscal operations for a 3,000-person MEU through a seven-month "
                "deployment aboard three naval vessels."
            ),
            "resume_pdf": (
                "Ran fiscal operations for a 3,000-person MEU through a seven-month "
                "deployment aboard three naval vessels."
            ),
        },
    },
    "usmc.meu.cash-custody": {
        "scope": "twenty_second_meu_deployed_cash_custody",
        "values": {
            "cash_budget": {
                "value": 350_000,
                "unit": "USD",
                "display": "$350,000",
            },
            "discrepancies": {
                "value": 0,
                "unit": "count",
                "display": "zero discrepancies",
            },
        },
        "renderings": {
            "about": "managed a $350,000 cash budget with zero discrepancies",
            "resume_source": (
                "Managed a \\$350,000 deployed cash budget with zero discrepancies"
            ),
            "resume_pdf": (
                "Managed a $350,000 deployed cash budget with zero discrepancies"
            ),
        },
    },
}
SCOPE_SUMMARIES = {
    "camp_lejeune_disbursing_office_role": (
        "Helping-leadership role in one Camp Lejeune disbursing office; no "
        "rank among Marine Corps offices is asserted."
    ),
    "twenty_second_meu_deployment": (
        "22d Marine Expeditionary Unit deployment duration, embarked vessels, "
        "and supported-unit size; no nation count is asserted."
    ),
    "twenty_second_meu_deployed_cash_custody": (
        "Deployed cash custody for the same MEU assignment: budget size and "
        "reconciliation outcome, not total unit spending."
    ),
}
EXCLUSION_REASONS = {
    "disbursing-office_rank": (
        "No public comparator scope is encoded for any office rank."
    ),
    "deployment_nation_count": (
        "No public counting rule is encoded for deployment nation totals."
    ),
}
VERIFICATION_SCOPE_SUMMARY = (
    "The release gate requires the typed claims to agree across the About page, "
    "Typst resume source, and text from the exact shipped PDF."
)
EVIDENCE_BOUNDARY_SUMMARY = (
    "The operator-authorized truth release identifies the public subset. The "
    "audit did not inspect and does not publish the underlying private service record."
)
REVIEW_BASIS_SUMMARY = (
    "Operator authorization preserves the common facts and removes the disputed "
    "office-rank and nation-count assertions."
)
PROVENANCE_SUMMARY = (
    "This claim is part of the operator-authorized public subset bound to the "
    "recorded truth-release digest."
)
SMALL_NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
}
TENS_NUMBER_WORDS = {
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
NUMBER_WORD_VALUES = SMALL_NUMBER_WORDS | TENS_NUMBER_WORDS
NUMBER_SCALES = {"hundred": 100, "thousand": 1_000, "million": 1_000_000}
NUMBER_WORD_ATOM = (
    r"(?:"
    + "|".join(sorted((*NUMBER_WORD_VALUES, *NUMBER_SCALES), key=len, reverse=True))
    + r")"
)
NUMBER_WORD_SEQUENCE = (
    rf"{NUMBER_WORD_ATOM}(?:(?:\s+|-)(?:and(?:\s+|-))?{NUMBER_WORD_ATOM})*"
)
NUMBER_TOKEN = rf"(?:[0-9][0-9,]*(?:\.[0-9]+)?|{NUMBER_WORD_SEQUENCE})"
QUANTITY_TOKEN = (
    rf"(?:{NUMBER_TOKEN}|(?:a\s+)?(?:couple|dozen|score)|dozens?|scores?|"
    r"few|half(?:\s+(?:a|an))?|many|multiple|several)"
)
DISPLAY_NUMBER = re.compile(rf"\$?(?P<number>{NUMBER_TOKEN})(?=\b)", re.IGNORECASE)
RANK_TOKEN = (
    rf"(?:(?:No\.?|number)\s*{NUMBER_TOKEN}|#\s*{NUMBER_TOKEN}|"
    rf"{NUMBER_TOKEN}(?:st|nd|rd|th)?[- ](?:largest|ranked))"
)
COMPARATOR_TOKEN = (
    r"(?:busiest|busier|largest|larger|most[- ]active|ranked|top(?:[- ]ranked)?|"
    r"(?:[a-z]+|[0-9]+(?:st|nd|rd|th)?)[- ](?:busiest|largest|ranked))"
)
EXCLUDED_PUBLIC_PATTERNS = (
    (
        "disbursing-office rank",
        re.compile(
            rf"\b{COMPARATOR_TOKEN}\b"
            r"[^.\n]{0,100}\bdisbursing office\b",
            re.IGNORECASE,
        ),
    ),
    (
        "disbursing-office rank",
        re.compile(
            r"\bdisbursing office\b[^.\n]{0,100}"
            rf"\b{COMPARATOR_TOKEN}\b",
            re.IGNORECASE,
        ),
    ),
    (
        "disbursing-office rank",
        re.compile(
            rf"(?:{RANK_TOKEN})[^.\n]{{0,100}}\bdisbursing office\b|"
            rf"\bdisbursing office\b[^.\n]{{0,100}}(?:{RANK_TOKEN})",
            re.IGNORECASE,
        ),
    ),
    (
        "deployment nation count",
        re.compile(
            rf"(?:\b{QUANTITY_TOKEN}\b[^.\n]{{0,80}}\b(?:countries|nations?)\b|"
            rf"\b(?:countries|nations?)\b[^.\n]{{0,80}}\b{QUANTITY_TOKEN}\b)",
            re.IGNORECASE,
        ),
    ),
)
RESIDUAL_CLAIM_PATTERNS = (
    (
        "Marine headcount",
        re.compile(
            rf"(?:\b{QUANTITY_TOKEN}\b[^.!?\n]{{0,100}}\bMarines\b|"
            rf"\bMarines\b[^.!?\n]{{0,100}}\b{QUANTITY_TOKEN}\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "civilian headcount",
        re.compile(
            rf"(?=[^.!?\n]{{0,180}}\bcivilians\b)"
            r"(?=[^.!?\n]{0,180}\b(?:command|had|office|disbursing|included|staffed|headcount|number|unit)\b)"
            rf"[^.!?\n]*\b{QUANTITY_TOKEN}\b[^.!?\n]*",
            re.IGNORECASE,
        ),
    ),
    (
        "finance-function count",
        re.compile(
            rf"(?:\b{QUANTITY_TOKEN}\b[^.!?\n]{{0,60}}\bfinance functions?\b|"
            rf"\bfinance functions?\b[^.!?\n]{{0,60}}\b{QUANTITY_TOKEN}\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "deployment duration",
        re.compile(
            r"(?=[^.!?\n]{0,180}\bdeployment\b)"
            r"(?=[^.!?\n]{0,180}\b(?:days?|weeks?|months?|years?)\b)"
            rf"[^.!?\n]*\b{QUANTITY_TOKEN}\b[^.!?\n]*",
            re.IGNORECASE,
        ),
    ),
    (
        "naval-vessel count",
        re.compile(
            r"(?=[^.!?\n]{0,180}\b(?:aboard|deployment|naval)\b)"
            r"(?=[^.!?\n]{0,180}\b(?:ships?|vessels?)\b)"
            rf"[^.!?\n]*\b{QUANTITY_TOKEN}\b[^.!?\n]*",
            re.IGNORECASE,
        ),
    ),
    (
        "MEU population",
        re.compile(
            rf"(?:\b{QUANTITY_TOKEN}-(?:person|people|personnel)\b[^.!?\n]{{0,80}}"
            r"\b(?:MEU|Marine Expeditionary Unit)\b|"
            rf"\b{QUANTITY_TOKEN}\b[^.!?\n]{{0,60}}\b(?:people|personnel)\b"
            r"[^.!?\n]{0,80}\b(?:MEU|Marine Expeditionary Unit)\b|"
            r"\b(?:MEU|Marine Expeditionary Unit)\b[^.!?\n]{0,100}"
            rf"\b{QUANTITY_TOKEN}\b[^.!?\n]{{0,60}}\b(?:people|personnel)\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "regional service-population count",
        re.compile(
            rf"\b{QUANTITY_TOKEN}(?:\+|-plus)?\s+"
            r"(?:personnel|service members)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "cash-budget amount",
        re.compile(
            rf"(?:(?:\${NUMBER_TOKEN}(?:[KkMm]|\s*(?:USD|dollars?))?|"
            rf"{QUANTITY_TOKEN}\s+dollars?)[^.!?\n]{{0,100}}\b(?:cash|budget|fund)\b|"
            rf"\b(?:cash|budget|fund)\b[^.!?\n]{{0,100}}(?:\${NUMBER_TOKEN}"
            rf"(?:[KkMm]|\s*(?:USD|dollars?))?|{QUANTITY_TOKEN}\s+dollars?))",
            re.IGNORECASE,
        ),
    ),
    (
        "discrepancy count",
        re.compile(
            rf"(?:\b{QUANTITY_TOKEN}\b[^.!?\n]{{0,60}}\bdiscrepanc(?:y|ies)\b|"
            rf"\bdiscrepanc(?:y|ies)\b[^.!?\n]{{0,60}}\b{QUANTITY_TOKEN}\b)",
            re.IGNORECASE,
        ),
    ),
)


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def strict_json(path: Path) -> tuple[object | None, bytes, list[str]]:
    errors: list[str] = []
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, b"", [f"{path}: cannot read authority: {exc}"]

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-JSON constant {value!r}")

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict:
        document: dict[str, object] = {}
        for key, value in pairs:
            if key in document:
                raise ValueError(f"duplicate key {key!r}")
            document[key] = value
        return document

    try:
        document = json.loads(
            raw,
            parse_constant=reject_constant,
            object_pairs_hook=reject_duplicates,
        )
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        errors.append(f"{path}: not strict JSON: {exc}")
        return None, raw, errors
    return document, raw, errors


def extract_pdf_text(path: Path) -> tuple[str, list[str]]:
    if not path.is_file() or path.is_symlink():
        return "", [f"{path}: shipped resume must be one regular PDF file"]
    try:
        completed = subprocess.run(
            ["pdftotext", str(path), "-"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return "", ["pdftotext is required to validate the shipped resume"]
    if completed.returncode != 0:
        detail = normalized(completed.stderr) or f"exit {completed.returncode}"
        return "", [f"{path}: pdftotext failed: {detail}"]
    return completed.stdout, []


def load_surfaces(root: Path, pdf_path: Path) -> tuple[dict[str, str], list[str]]:
    errors: list[str] = []
    surfaces: dict[str, str] = {}
    for surface in ("about", "resume_source"):
        path = root / SURFACE_PATHS[surface]
        try:
            surfaces[surface] = normalized(path.read_text())
        except OSError as exc:
            errors.append(f"{path}: cannot read claim surface: {exc}")
    pdf_text, pdf_errors = extract_pdf_text(pdf_path)
    errors.extend(pdf_errors)
    surfaces["resume_pdf"] = normalized(pdf_text)
    return surfaces, errors


def parse_date(value: object, label: str, errors: list[str]) -> dt.date | None:
    if not isinstance(value, str):
        errors.append(f"{label} must be an ISO YYYY-MM-DD string")
        return None
    try:
        parsed = dt.date.fromisoformat(value)
    except ValueError:
        errors.append(f"{label} must be an ISO YYYY-MM-DD string")
        return None
    if parsed.isoformat() != value:
        errors.append(f"{label} must use canonical zero-padded YYYY-MM-DD form")
        return None
    return parsed


def display_numbers(text: str) -> list[int | float]:
    values: list[int | float] = []
    for match in DISPLAY_NUMBER.finditer(text):
        token = match.group("number").replace(",", "").casefold()
        if token[0].isdigit():
            values.append(float(token) if "." in token else int(token))
            continue
        total = 0
        current = 0
        for word in re.split(r"[\s-]+", token):
            if word == "and":
                continue
            if word in NUMBER_WORD_VALUES:
                current += NUMBER_WORD_VALUES[word]
            elif word == "hundred":
                current = max(current, 1) * NUMBER_SCALES[word]
            else:
                total += max(current, 1) * NUMBER_SCALES[word]
                current = 0
        values.append(total + current)
    return values


def reject_excluded_assertions(label: str, text: str, errors: list[str]) -> None:
    for phrase in FORBIDDEN_PUBLIC_VARIANTS:
        if phrase.casefold() in text.casefold():
            errors.append(f"{label} retains excluded public career wording {phrase!r}")
    for topic, pattern in EXCLUDED_PUBLIC_PATTERNS:
        match = pattern.search(text)
        if match is not None:
            errors.append(f"{label} asserts excluded {topic}: {match.group(0)!r}")


def validate_manifest(
    document: object,
    surfaces: dict[str, str],
    *,
    as_of: dt.date,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(document, dict):
        return ["career claim authority must be one JSON object"]
    if set(document) != TOP_LEVEL_KEYS:
        errors.append("career claim authority has unexpected or missing top-level keys")
    if (
        type(document.get("schema_version")) is not int
        or document.get("schema_version") != SCHEMA_VERSION
    ):
        errors.append(f"career claim schema_version must be integer {SCHEMA_VERSION}")
    if document.get("verification_scope") != EXPECTED_VERIFICATION_SCOPE:
        errors.append(
            "career claim verification_scope must equal the closed surface registry"
        )
    if document.get("evidence_boundary") != EXPECTED_EVIDENCE_BOUNDARY:
        errors.append(
            "career claim evidence_boundary must equal the closed inspection boundary"
        )

    evidence_authorities = document.get("evidence_authorities")
    if not isinstance(evidence_authorities, list) or not evidence_authorities:
        errors.append("evidence_authorities must be a nonempty array")
        evidence_authorities = []
    evidence_ids: set[str] = set()
    for index, authority in enumerate(evidence_authorities):
        label = f"evidence_authorities[{index}]"
        if not isinstance(authority, dict) or set(authority) != EVIDENCE_AUTHORITY_KEYS:
            errors.append(f"{label} has unexpected or missing keys")
            continue
        authority_id = authority.get("id")
        if isinstance(authority_id, str):
            if authority_id in evidence_ids:
                errors.append(f"duplicate evidence authority id {authority_id!r}")
            evidence_ids.add(authority_id)
        recorded_at = parse_date(
            authority.get("recorded_at"), f"{label}.recorded_at", errors
        )
        if recorded_at is not None and recorded_at > as_of:
            errors.append(f"{label}.recorded_at cannot be later than {as_of}")
        if authority != EXPECTED_EVIDENCE_AUTHORITY:
            errors.append(
                f"{label} must equal the recorded operator-authority contract"
            )
    if evidence_ids != {AUTHORITY_ID}:
        errors.append(
            "evidence authority IDs differ: "
            f"expected {[AUTHORITY_ID]!r}, "
            f"found {sorted(evidence_ids)!r}"
        )

    excluded = document.get("excluded_public_claims")
    if not isinstance(excluded, list) or not excluded:
        errors.append("excluded_public_claims must be a nonempty array")
        excluded = []
    for index, item in enumerate(excluded):
        label = f"excluded_public_claims[{index}]"
        if not isinstance(item, dict) or set(item) != {"topic", "decision"}:
            errors.append(f"{label} must contain only topic and decision")
            continue
    if excluded != EXPECTED_EXCLUDED_PUBLIC_CLAIMS:
        errors.append("excluded public claim contract differs from the closed registry")

    claims = document.get("claims")
    if not isinstance(claims, list) or not claims:
        errors.append("claims must be a nonempty array")
        claims = []
    claim_ids: set[str] = set()
    approved_displays_by_surface: dict[str, list[str]] = {
        surface: [] for surface in SURFACE_PATHS
    }
    for index, claim in enumerate(claims):
        label = f"claims[{index}]"
        if not isinstance(claim, dict) or set(claim) != CLAIM_KEYS:
            errors.append(f"{label} has unexpected or missing keys")
            continue
        claim_id = claim.get("id")
        expected_claim: dict | None = None
        expected_values: dict[str, dict] | None = None
        if not isinstance(claim_id, str) or not CLAIM_ID.fullmatch(claim_id):
            errors.append(f"{label}.id must be a stable dotted or dashed lowercase ID")
        elif claim_id in claim_ids:
            errors.append(f"duplicate claim id {claim_id!r}")
        else:
            claim_ids.add(claim_id)
            expected_claim = EXPECTED_CLAIMS.get(claim_id)
            if expected_claim is None:
                errors.append(f"unexpected claim id {claim_id!r}")
            else:
                expected_values = expected_claim["values"]
        if expected_claim is not None and claim.get("scope") != expected_claim["scope"]:
            errors.append(
                f"{label}.scope must be the registered scope code "
                f"{expected_claim['scope']!r}"
            )
        evidence_ref = claim.get("evidence_ref")
        if evidence_ref != AUTHORITY_ID or evidence_ref not in evidence_ids:
            errors.append(
                f"{label}.evidence_ref must resolve to the recorded operator authority"
            )

        provenance = claim.get("provenance")
        provenance_recorded_at: dt.date | None = None
        if not isinstance(provenance, dict) or set(provenance) != PROVENANCE_KEYS:
            errors.append(f"{label}.provenance has unexpected or missing keys")
        else:
            if provenance != EXPECTED_PROVENANCE:
                errors.append(
                    f"{label}.provenance must equal the closed authority binding"
                )
            provenance_recorded_at = parse_date(
                provenance.get("recorded_at"),
                f"{label}.provenance.recorded_at",
                errors,
            )

        verified_at = parse_date(
            claim.get("verified_at"), f"{label}.verified_at", errors
        )
        valid_through = parse_date(
            claim.get("valid_through"), f"{label}.valid_through", errors
        )
        if verified_at is not None and verified_at > as_of:
            errors.append(f"{label}.verified_at cannot be later than {as_of}")
        if provenance_recorded_at is not None and verified_at is not None:
            if provenance_recorded_at != verified_at:
                errors.append(f"{label}.provenance.recorded_at must equal verified_at")
        if valid_through is not None and valid_through < as_of:
            errors.append(
                f"{label} verification expired on {valid_through}; operator review is required"
            )
        if verified_at is not None and valid_through is not None:
            if valid_through < verified_at:
                errors.append(f"{label}.valid_through precedes verified_at")
            elif (valid_through - verified_at).days > 366:
                errors.append(f"{label} verification window may not exceed 366 days")

        values = claim.get("values")
        if not isinstance(values, list) or not values:
            errors.append(f"{label}.values must be a nonempty array")
            values = []
        value_names: set[str] = set()
        valid_values: list[dict] = []
        for value_index, value in enumerate(values):
            value_label = f"{label}.values[{value_index}]"
            if not isinstance(value, dict) or set(value) != {
                "name",
                "value",
                "unit",
                "display",
            }:
                errors.append(
                    f"{value_label} must contain only name, value, unit, and display"
                )
                continue
            name = value.get("name")
            if not isinstance(name, str) or not VALUE_NAME.fullmatch(name):
                errors.append(f"{value_label}.name must be lowercase snake_case")
            elif name in value_names:
                errors.append(f"{label} has duplicate value name {name!r}")
            else:
                value_names.add(name)
            typed_value = value.get("value")
            if type(typed_value) is not int or typed_value < 0:
                errors.append(f"{value_label}.value must be a nonnegative integer")
            unit = value.get("unit")
            display = value.get("display")
            if not nonempty_string(unit):
                errors.append(f"{value_label}.unit must be a nonempty string")
            if not nonempty_string(display):
                errors.append(f"{value_label}.display must be a nonempty string")
            if expected_values is not None and isinstance(name, str):
                expected_value = expected_values.get(name)
                if expected_value is None:
                    errors.append(f"{claim_id} has unexpected value name {name!r}")
                else:
                    if typed_value != expected_value["value"]:
                        errors.append(
                            f"{value_label}.value must be authority-bound value "
                            f"{expected_value['value']!r}, found {typed_value!r}"
                        )
                    if unit != expected_value["unit"]:
                        errors.append(
                            f"{value_label}.unit must be {expected_value['unit']!r}, "
                            f"found {unit!r}"
                        )
                    if display != expected_value["display"]:
                        errors.append(
                            f"{value_label}.display must be authority-bound display "
                            f"{expected_value['display']!r}, found {display!r}"
                        )
            if type(typed_value) is int and isinstance(display, str):
                parsed = display_numbers(display)
                if parsed != [typed_value]:
                    errors.append(
                        f"{value_label}.display must encode exactly typed value "
                        f"{typed_value}; parsed {parsed!r}"
                    )
            valid_values.append(value)
        if expected_values is not None and value_names != set(expected_values):
            errors.append(
                f"{claim_id} value names differ: expected "
                f"{sorted(expected_values)!r}, found {sorted(value_names)!r}"
            )

        renderings = claim.get("renderings")
        if not isinstance(renderings, list):
            errors.append(f"{label}.renderings must be an array")
            renderings = []
        by_surface: dict[str, str] = {}
        for rendering_index, rendering in enumerate(renderings):
            rendering_label = f"{label}.renderings[{rendering_index}]"
            if not isinstance(rendering, dict) or set(rendering) != {
                "surface",
                "path",
                "text",
            }:
                errors.append(
                    f"{rendering_label} must contain only surface, path, and text"
                )
                continue
            surface = rendering.get("surface")
            if surface not in SURFACE_PATHS:
                errors.append(f"{rendering_label}.surface is not recognized")
                continue
            if surface in by_surface:
                errors.append(f"{label} has duplicate rendering surface {surface!r}")
                continue
            if rendering.get("path") != SURFACE_PATHS[surface]:
                errors.append(
                    f"{rendering_label}.path must be {SURFACE_PATHS[surface]!r}"
                )
            text = rendering.get("text")
            if not nonempty_string(text):
                errors.append(f"{rendering_label}.text must be a nonempty string")
                continue
            normalized_text = normalized(text)
            if (
                expected_claim is not None
                and normalized_text != expected_claim["renderings"][surface]
            ):
                errors.append(
                    f"{rendering_label}.text must equal the authority-bound "
                    f"{surface} rendering"
                )
            by_surface[surface] = normalized_text
        if set(by_surface) != set(SURFACE_PATHS):
            errors.append(
                f"{label} must map exactly about, resume_source, and resume_pdf"
            )
        for surface, expected in by_surface.items():
            actual = surfaces.get(surface, "")
            count = actual.count(expected)
            if count != 1:
                errors.append(
                    f"{claim_id or label}: {surface} must contain its exact rendering once; found {count}"
                )
            typed_numbers = [
                value["value"]
                for value in valid_values
                if type(value.get("value")) is int
            ]
            parsed_numbers = display_numbers(expected)
            if Counter(parsed_numbers) != Counter(typed_numbers):
                errors.append(
                    f"{claim_id or label}: {surface} rendering numeric multiset "
                    f"must equal typed values {typed_numbers!r}; parsed "
                    f"{parsed_numbers!r}"
                )
            for value in valid_values:
                display = value.get("display")
                if (
                    isinstance(display, str)
                    and display.casefold() not in expected.casefold()
                ):
                    errors.append(
                        f"{claim_id or label}: {surface} does not render typed value "
                        f"{display!r}"
                    )
                elif count == 1 and isinstance(display, str):
                    approved_displays_by_surface[surface].append(display)

    if claim_ids != set(EXPECTED_CLAIMS):
        errors.append(
            "claim IDs differ: "
            f"expected {sorted(EXPECTED_CLAIMS)!r}, found {sorted(claim_ids)!r}"
        )

    for surface, text in surfaces.items():
        reject_excluded_assertions(surface, text, errors)
        residual = text
        for display in approved_displays_by_surface.get(surface, []):
            residual = re.sub(re.escape(display), " ", residual, count=1, flags=re.I)
        for topic, pattern in RESIDUAL_CLAIM_PATTERNS:
            match = pattern.search(residual)
            if match is not None:
                errors.append(
                    f"{surface} contains unmanaged {topic} wording outside the "
                    f"approved rendering: {match.group(0)!r}"
                )

    return errors


def build_receipt(document: dict, authority_bytes: bytes) -> dict:
    claims = []
    for claim in document["claims"]:
        claims.append(
            {
                "evidence_ref": claim["evidence_ref"],
                "id": claim["id"],
                "provenance": {
                    **claim["provenance"],
                    "summary": PROVENANCE_SUMMARY,
                },
                "scope": {
                    "code": claim["scope"],
                    "summary": SCOPE_SUMMARIES[claim["scope"]],
                },
                "valid_through": claim["valid_through"],
                "values": [
                    {
                        "display": value["display"],
                        "name": value["name"],
                        "unit": value["unit"],
                        "value": value["value"],
                    }
                    for value in claim["values"]
                ],
                "verified_at": claim["verified_at"],
            }
        )
    return {
        "$schema_note": "Generated public receipt; data/career-claims.json is authoritative.",
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "authority_sha256": hashlib.sha256(authority_bytes).hexdigest(),
        "verification_scope": {
            "surfaces": document["verification_scope"],
            "summary": VERIFICATION_SCOPE_SUMMARY,
        },
        "evidence_boundary": {
            **document["evidence_boundary"],
            "summary": EVIDENCE_BOUNDARY_SUMMARY,
        },
        "evidence_authorities": [
            {**authority, "review_summary": REVIEW_BASIS_SUMMARY}
            for authority in document["evidence_authorities"]
        ],
        "excluded_public_claims": [
            {**item, "reason": EXCLUSION_REASONS[item["topic"]]}
            for item in document["excluded_public_claims"]
        ],
        "claims": claims,
    }


def serialize_receipt(document: dict) -> bytes:
    return (
        json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")


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


def resolve(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    parser.add_argument("--authority", type=Path, default=AUTHORITY_PATH)
    parser.add_argument("--pdf", type=Path, default=PDF_PATH)
    parser.add_argument("--output", type=Path, default=RECEIPT_PATH)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--as-of", type=dt.date.fromisoformat, default=dt.date.today())
    args = parser.parse_args()
    root = args.root.resolve()
    authority_path = resolve(root, args.authority)
    pdf_path = resolve(root, args.pdf)
    output_path = resolve(root, args.output)

    document, authority_bytes, errors = strict_json(authority_path)
    surfaces, surface_errors = load_surfaces(root, pdf_path)
    errors.extend(surface_errors)
    if document is not None:
        errors.extend(validate_manifest(document, surfaces, as_of=args.as_of))
    if errors:
        for error in errors:
            sys.stderr.write(f"ERROR: {error}\n")
        return 1
    assert isinstance(document, dict)
    expected = serialize_receipt(build_receipt(document, authority_bytes))
    if args.check:
        if not check_output(output_path, expected, root):
            return 1
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(expected)
    sys.stdout.write("PASS: typed career-claim authority and shipped PDF\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
