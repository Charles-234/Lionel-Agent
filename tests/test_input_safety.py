"""Focused tests for the input safety screen.

The screen only checks shape, cleans display text, and labels proof.
It never authorizes, plans, runs, or audits, so these tests assert
refusals, cleaning, and fail-closed proof labels only.
"""

import unittest

from agent.safety import (
    SafetyError,
    check_request,
    sanitize_for_display,
    verification_status,
)


class InputSafetyTests(unittest.TestCase):
    def test_check_accepts_plain_words(self):
        self.assertEqual(check_request("  hello   world ").cleaned_text, "hello world")

    def test_check_refuses_empty(self):
        with self.assertRaises(SafetyError):
            check_request("    ")

    def test_check_refuses_wrong_type(self):
        with self.assertRaises(SafetyError):
            check_request({"text": "hello"})

    def test_check_refuses_oversized_input(self):
        with self.assertRaises(SafetyError):
            check_request("x" * 10_001)

    def test_sanitize_hides_secret_and_controls(self):
        dirty = "api_key=sk-abcdef123456\x00 hello"
        cleaned = sanitize_for_display(dirty)
        self.assertNotIn("sk-abcdef123456", cleaned)
        self.assertNotIn("\x00", cleaned)

    def test_sanitize_caps_length(self):
        self.assertTrue(sanitize_for_display("y" * 2_000).endswith("..."))

    def test_verify_never_trusts_simulation(self):
        verdict = verification_status(success=True, evidence_present=True,
                                      execution_mode="simulation")
        self.assertEqual(verdict.status, "UNVERIFIED")

    def test_verify_needs_success_and_evidence(self):
        self.assertEqual(
            verification_status(success=True, evidence_present=True,
                                execution_mode="real").status, "VERIFIED")
        self.assertEqual(
            verification_status(success=False, evidence_present=True,
                                execution_mode="real").status, "UNVERIFIED")
        self.assertEqual(
            verification_status(success=True, evidence_present=False,
                                execution_mode="real").status, "UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
