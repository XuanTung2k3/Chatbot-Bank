import importlib.util
import tempfile
import unittest
from pathlib import Path


TESTS_ROOT = Path(__file__).resolve().parent
FLOW_PATH = TESTS_ROOT / "chatbot_test_flow.py"


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("chatbot_test_flow_module", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ChatbotTestFlowAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.flow = load_module(FLOW_PATH)
        cls.corpus = cls.flow.load_corpus()

    def test_corpus_has_expected_topic_shape(self):
        self.assertEqual(len(self.corpus["topic_buckets"]), 10)
        for bucket in self.corpus["topic_buckets"]:
            self.assertEqual(len(bucket["questions"]), 10, msg=bucket["topic_id"])
        self.assertEqual(len(self.corpus["mixed_social_regression"]), 10)

    def test_prepare_sheet_row_count_matches_modes_and_channels(self):
        rows = self.flow.build_sheet_rows(
            self.corpus,
            modes=["empathetic", "nonempathetic"],
            channels=["website", "api"],
            include_mixed_social=True,
            run_id="test_run",
        )
        self.assertEqual(len(rows), 440)

    def test_variant_filter_can_target_mixed_social_only(self):
        rows = self.flow.build_sheet_rows(
            self.corpus,
            modes=["empathetic"],
            channels=["api"],
            include_mixed_social=True,
            variant_types=["mixed_social"],
        )
        self.assertEqual(len(rows), 10)
        self.assertTrue(all(row["variant_type"] == "mixed_social" for row in rows))

    def test_parse_questions_file_keeps_sections_and_questions(self):
        content = "\n".join(
            [
                "1. Account opening and onboarding",
                "How do I open a bank account with you?",
                "What documents do I need to open a checking account?",
                "",
                "2. Savings and deposits",
                "What savings accounts do you offer?",
            ]
        )
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        try:
            records = self.flow.parse_questions_file(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

        self.assertEqual(len(records), 3)
        self.assertEqual(records[0]["section_title"], "Account opening and onboarding")
        self.assertEqual(records[2]["section_title"], "Savings and deposits")
        self.assertEqual(records[0]["question_id"], "q001")
        self.assertEqual(records[2]["question_id"], "q003")

    def test_extract_api_endpoint_from_text_supports_website_html(self):
        html = """
        <html>
          <body>
            <script>
              const API_ENDPOINT = "https://m-finance-137003227004.us-central1.run.app";
            </script>
          </body>
        </html>
        """
        endpoint = self.flow._extract_api_endpoint_from_text(html)
        self.assertEqual(endpoint, "https://m-finance-137003227004.us-central1.run.app")

    def test_question_file_summary_counts_errors(self):
        rows = [
            {"mode": "empathetic", "response": "ok", "transport_error": "", "turn_classification": "substantive"},
            {"mode": "empathetic", "response": "", "transport_error": "timeout", "turn_classification": ""},
            {"mode": "nonempathetic", "response": "ok", "transport_error": "", "turn_classification": "greeting_only"},
        ]
        summary = self.flow.summarize_question_file_rows(rows)
        self.assertEqual(summary["empathetic"]["total"], 2)
        self.assertEqual(summary["empathetic"]["transport_error"], 1)
        self.assertEqual(summary["empathetic"]["empty_response"], 1)
        self.assertEqual(summary["nonempathetic"]["non_substantive_turn"], 1)

    def test_question_file_runner_retries_timeout_and_keeps_answer(self):
        attempts = {"count": 0}
        original_post_json = self.flow.post_json
        original_load_endpoints = self.flow.load_endpoints
        self.flow.load_endpoints = lambda overrides=None: {"empathetic": "https://example.com"}

        def fake_post_json(endpoint, payload, timeout=25):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise TimeoutError("timed out")
            return {
                "response": "Recovered answer",
                "response_mode": "playbook",
                "turn_classification": "substantive",
                "grounding_scope": "playbook",
                "cache_hit": False,
                "cache_version": "v10",
                "userHash": payload["userHash"],
            }

        self.flow.post_json = fake_post_json
        try:
            rows = self.flow.run_api_questions_file(
                questions=[
                    {
                        "section_index": "1",
                        "section_title": "Account opening",
                        "question_index": "1",
                        "question_id": "q001",
                        "question": "How do I open a bank account with you?",
                    }
                ],
                modes=["empathetic"],
                timeout_sec=1,
                max_attempts=3,
                retry_delay_ms=0,
                endpoint_overrides={"empathetic": "https://example.com"},
            )
        finally:
            self.flow.post_json = original_post_json
            self.flow.load_endpoints = original_load_endpoints

        self.assertEqual(attempts["count"], 2)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["response"], "Recovered answer")
        self.assertEqual(rows[0]["transport_error"], "")
        self.assertEqual(rows[0]["attempt_count"], "2")
        self.assertIn("attempts=2", rows[0]["notes"])

    def test_grade_question_file_rows_adds_verdict_fields(self):
        rows = [
            {
                "run_id": "qfile_test",
                "mode": "empathetic",
                "requested_target": "https://vincent-bank-empathetic.web.app/",
                "endpoint": "https://example.com",
                "section_index": "1",
                "section_title": "Account opening and onboarding",
                "question_index": "1",
                "question_id": "q001",
                "question": "How do I open a bank account with you?",
                "session_id": "abc",
                "response": "For a new checking or payment account, the usual starting documents are a valid identification document, proof of address, and any tax or identity number required by local regulation.",
                "response_mode": "playbook",
                "turn_classification": "substantive",
                "grounding_scope": "playbook",
                "cache_hit": "False",
                "cache_version": "v10",
                "attempt_count": "1",
                "transport_error": "",
                "notes": "",
            }
        ]
        graded = self.flow.grade_question_file_rows(rows, self.corpus)
        self.assertEqual(len(graded), 1)
        self.assertEqual(graded[0]["expectation_type"], "official_rag_expected")
        self.assertEqual(graded[0]["verdict"], "Pass")
        self.assertEqual(graded[0]["error_type"], "")

    def test_grade_question_file_rows_flags_unmatched_questions(self):
        rows = [
            {
                "run_id": "qfile_test",
                "mode": "empathetic",
                "requested_target": "https://vincent-bank-empathetic.web.app/",
                "endpoint": "https://example.com",
                "section_index": "99",
                "section_title": "Other",
                "question_index": "999",
                "question_id": "q999",
                "question": "This question is not in the corpus?",
                "session_id": "abc",
                "response": "This is an English answer.",
                "response_mode": "generated",
                "turn_classification": "substantive",
                "grounding_scope": "model_only",
                "cache_hit": "False",
                "cache_version": "v10",
                "attempt_count": "1",
                "transport_error": "",
                "notes": "",
            }
        ]
        graded = self.flow.grade_question_file_rows(rows, self.corpus)
        self.assertEqual(graded[0]["topic_id"], "unmapped_question_file")
        self.assertIn("unmatched_question_in_corpus_lookup", graded[0]["notes"])

    def test_misclassified_turn_is_flagged_as_fail(self):
        record = {
            "topic_id": "account_opening_onboarding",
            "topic_label": "Account opening and onboarding",
            "question_id": "mixed_social_01",
            "question": "Hi, how do I open a bank account with you?",
            "variant_type": "mixed_social",
            "expectation_type": "official_rag_expected",
            "expected_answer_core": "Treat this as substantive.",
            "official_reference_url": "",
            "website_session_group": "mixed_social_regression",
            "website_session_order": "11",
        }
        response = {
            "response": "Hello. Provide an AmazingBank service or question to continue.",
            "turn_classification": "greeting_only",
            "grounding_scope": "policy",
            "response_mode": "policy",
            "cache_hit": False,
            "userHash": "123",
        }
        result = self.flow.evaluate_api_result("empathetic", record, response, endpoint="https://example.com")
        self.assertEqual(result["verdict"], "Fail")
        self.assertEqual(result["error_type"], "misclassified_turn")
        self.assertEqual(result["suspected_layer"], "turn_classifier_or_routing")

    def test_wrong_language_is_flagged_as_fail(self):
        record = {
            "topic_id": "support",
            "topic_label": "Customer support and branch service",
            "question_id": "support_07",
            "question": "What are your customer service hours?",
            "variant_type": "canonical",
            "expectation_type": "live_or_strict_grounding",
            "expected_answer_core": "Only provide grounded hours.",
            "official_reference_url": "",
            "website_session_group": "support",
            "website_session_order": "8",
        }
        response = {
            "response": "Gio ho tro khach hang la tu thu hai den thu sau.",
            "turn_classification": "substantive",
            "grounding_scope": "official_rag",
            "response_mode": "generated",
            "cache_hit": False,
            "userHash": "123",
        }
        result = self.flow.evaluate_api_result("empathetic", record, response, endpoint="https://example.com")
        self.assertEqual(result["verdict"], "Fail")
        self.assertEqual(result["error_type"], "wrong_language")

    def test_unsupported_specific_claim_is_flagged(self):
        record = {
            "topic_id": "savings_deposits",
            "topic_label": "Savings and deposits",
            "question_id": "savings_02",
            "question": "What is the interest rate on your basic savings account?",
            "variant_type": "canonical",
            "expectation_type": "live_or_strict_grounding",
            "expected_answer_core": "Only provide exact rate if grounded.",
            "official_reference_url": "",
            "website_session_group": "savings_deposits",
            "website_session_order": "2",
        }
        response = {
            "response": "The savings rate is 4.25% right now.",
            "turn_classification": "substantive",
            "grounding_scope": "model_only",
            "response_mode": "generated",
            "cache_hit": False,
            "userHash": "123",
        }
        result = self.flow.evaluate_api_result("nonempathetic", record, response, endpoint="https://example.com")
        self.assertEqual(result["verdict"], "Fail")
        self.assertEqual(result["error_type"], "unsupported_specific_claim")
        self.assertEqual(result["suspected_layer"], "grounding_policy_or_generation")


if __name__ == "__main__":
    unittest.main()
