#!/usr/bin/env python3
"""fetch()'s retry policy: 5xx is retried, every other outcome is answered once."""

# WHY this exists: a single `unexpected GitHub API status 504` on one repository turned into a
# hard UNVERIFIED and failed the deploy gate for a branch whose own content was fine. A 5xx is
# the one status that says nothing about the subject being witnessed. Every other outcome is
# informative and must NOT be retried -- retrying a 404 spends time re-learning that the repo is
# still absent, and retrying a 403 burns the rate limit that caused it.
#
# The contract is deliberately unchanged when the retries run out: this witness exists so a public
# numeric claim is checked against reality, and a claim nobody could verify has not passed.

import importlib.util
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
TARGET = REPO / "bin/validate-fleet-counts.py"

_loader = SourceFileLoader("validate_fleet_counts", str(TARGET))
_spec = importlib.util.spec_from_loader("validate_fleet_counts", _loader)
vfc = importlib.util.module_from_spec(_spec)
_loader.exec_module(vfc)


class FetchRetryPolicy(unittest.TestCase):
    def run_fetch(self, statuses: list[int | None]):
        """Drive fetch() with a scripted sequence of fetch_once outcomes."""
        calls = []

        def fake_once(url, token):
            calls.append(url)
            status = statuses[min(len(calls) - 1, len(statuses) - 1)]
            return status, b"{}"

        with (
            mock.patch.object(vfc, "fetch_once", fake_once),
            mock.patch.object(vfc.time, "sleep", lambda _s: None),
        ):
            status, _ = vfc.fetch("https://api.github.com/repos/o/r", None)
        return status, len(calls)

    def test_a_transient_5xx_then_success_is_retried_and_succeeds(self):
        status, calls = self.run_fetch([504, 200])
        self.assertEqual(status, 200)
        self.assertEqual(calls, 2)

    def test_a_persistent_5xx_still_fails_after_the_attempts(self):
        # The contract is preserved: exhausted retries surface the 5xx, which witness_repo
        # turns into UNVERIFIED. Retry removes the transient failure, not the requirement.
        status, calls = self.run_fetch([503])
        self.assertEqual(status, 503)
        self.assertEqual(calls, vfc.FETCH_ATTEMPTS)

    def test_a_404_is_answered_once_and_never_retried(self):
        # POSITIVE CONTROL against over-retrying: a 404 is a real answer about the repository.
        status, calls = self.run_fetch([404])
        self.assertEqual(status, 404)
        self.assertEqual(calls, 1)

    def test_a_403_is_answered_once(self):
        status, calls = self.run_fetch([403])
        self.assertEqual(status, 403)
        self.assertEqual(calls, 1)

    def test_success_is_answered_once(self):
        status, calls = self.run_fetch([200])
        self.assertEqual(status, 200)
        self.assertEqual(calls, 1)

    def test_an_unreachable_host_is_not_retried(self):
        # status None means the request never reached GitHub. That is not a 5xx and is left alone.
        status, calls = self.run_fetch([None])
        self.assertIsNone(status)
        self.assertEqual(calls, 1)

    def test_witness_repo_still_reports_a_persistent_5xx_as_an_error(self):
        with (
            mock.patch.object(vfc, "fetch_once", lambda u, t: (502, b"{}")),
            mock.patch.object(vfc.time, "sleep", lambda _s: None),
        ):
            private, ci, error = vfc.witness_repo("o", "r", check_kanon_ci=False, token=None)
        self.assertIsNone(private)
        self.assertIsNone(ci)
        self.assertIn("502", error or "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
