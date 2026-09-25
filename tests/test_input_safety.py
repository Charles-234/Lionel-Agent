"""Focused tests for the input safety screen.

The screen only checks shape, cleans display text, and labels proof.
It never authorizes, plans, runs, or audits, so these tests assert
refusals, cleaning, and fail-closed proof labels only.
"""

import unittest

from agent.safety import (
    MAX_DISPLAY_CHARS,
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
        large = "y" * (MAX_DISPLAY_CHARS + 100)
        self.assertTrue(sanitize_for_display(large).endswith("..."))

    def test_sanitize_removes_hidden_reasoning_blocks(self):
        dirty = "<think>private scratch work</think>Final answer: The file is valid."
        cleaned = sanitize_for_display(dirty)
        self.assertNotIn("private scratch work", cleaned)
        self.assertIn("Final answer: The file is valid.", cleaned)

    def test_sanitize_removes_labeled_reasoning_before_answer(self):
        dirty = "Thinking: compare every possibility first.\nAnswer: It is a PDF."
        cleaned = sanitize_for_display(dirty)
        self.assertEqual(cleaned, "It is a PDF.")

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
