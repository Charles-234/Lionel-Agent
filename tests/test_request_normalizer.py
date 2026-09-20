import unittest
from unittest.mock import patch

from agent.request_normalizer import (
    EMPTY_REQUEST_MESSAGE,
    INVALID_TASK_TYPE_MESSAGE,
    NormalizedRequest,
    RequestNormalizationError,
    normalize_request,
)


class RequestNormalizerTests(unittest.TestCase):
    def test_valid_request_normalization(self):
        request = normalize_request(
            "Assess the authorized target",
            task_type="reconnaissance",
        )

        self.assertEqual(
            request,
            NormalizedRequest(
                raw_text="Assess the authorized target",
                objective="Assess the authorized target",
                task_type="reconnaissance",
            ),
        )

    def test_whitespace_is_normalized_without_changing_raw_text(self):
        raw_text = "  Assess\n\tthe   authorized target  "

        request = normalize_request(raw_text)

        self.assertEqual(request.raw_text, raw_text)
        self.assertEqual(request.objective, "Assess the authorized target")
        self.assertIsNone(request.task_type)

    def test_task_type_is_normalized(self):
        request = normalize_request(
            "Assess the authorized target",
            task_type=" Security-Testing ",
        )

        self.assertEqual(request.task_type, "security_testing")

    def test_empty_request_is_rejected_with_safe_deterministic_message(self):
        with self.assertRaisesRegex(RequestNormalizationError, EMPTY_REQUEST_MESSAGE):
            normalize_request(" \n\t ")

    def test_invalid_task_type_is_rejected_with_safe_deterministic_message(self):
        with self.assertRaisesRegex(RequestNormalizationError, INVALID_TASK_TYPE_MESSAGE):
            normalize_request("Review this request", task_type="administrator")

    def test_original_user_objective_is_preserved(self):
        raw_text = "Please   review\nthis exact request."

        request = normalize_request(raw_text)

        self.assertEqual(request.raw_text, raw_text)

    def test_normalization_is_deterministic(self):
        first = normalize_request("  Review   this request ", task_type=" RESEARCH ")
        second = normalize_request("  Review   this request ", task_type=" RESEARCH ")

        self.assertEqual(first, second)

    def test_normalization_cannot_execute_tools(self):
        with patch("tools.executor.execute") as execute:
            normalize_request("Assess the authorized target", task_type="reconnaissance")

        execute.assert_not_called()

    def test_normalization_does_not_authorize_capabilities(self):
        with patch("agent_registry.authorization.authorize_role_capability") as authorize:
            normalize_request("Assess the authorized target", task_type="reconnaissance")

        authorize.assert_not_called()


if __name__ == "__main__":
    unittest.main()
