import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path


FINANCE_ROOT = Path(__file__).resolve().parents[1]
EMPATHETIC_BACKEND = FINANCE_ROOT / "Empathetic" / "Backend"
NONEMPATHETIC_BACKEND = FINANCE_ROOT / "NonEmpathetic" / "Backend"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_rag_module(name: str, path: Path):
    original_requests = sys.modules.get("requests")
    original_official_domains = os.environ.get("OFFICIAL_BANK_DOMAINS")
    original_source_bank_name = os.environ.get("SOURCE_BANK_NAME")
    original_source_bank_short_name = os.environ.get("SOURCE_BANK_SHORT_NAME")

    sys.modules["requests"] = types.SimpleNamespace(get=lambda *args, **kwargs: None)
    os.environ["OFFICIAL_BANK_DOMAINS"] = "techcombank.com,www.techcombank.com"
    os.environ.pop("SOURCE_BANK_NAME", None)
    os.environ.pop("SOURCE_BANK_SHORT_NAME", None)

    try:
        return load_module(name, path)
    finally:
        if original_requests is not None:
            sys.modules["requests"] = original_requests
        else:
            sys.modules.pop("requests", None)

        if original_official_domains is None:
            os.environ.pop("OFFICIAL_BANK_DOMAINS", None)
        else:
            os.environ["OFFICIAL_BANK_DOMAINS"] = original_official_domains

        if original_source_bank_name is None:
            os.environ.pop("SOURCE_BANK_NAME", None)
        else:
            os.environ["SOURCE_BANK_NAME"] = original_source_bank_name

        if original_source_bank_short_name is None:
            os.environ.pop("SOURCE_BANK_SHORT_NAME", None)
        else:
            os.environ["SOURCE_BANK_SHORT_NAME"] = original_source_bank_short_name


def load_backend_main(name: str, path: Path):
    original_modules = {
        module_name: sys.modules.get(module_name)
        for module_name in [
            "functions_framework",
            "vertexai",
            "vertexai.preview",
            "vertexai.preview.generative_models",
            "vertexai.generative_models",
            "google",
            "google.cloud",
            "google.cloud.firestore",
            "flask",
            "requests",
            "banking_playbooks",
            "rag_retriever",
            "turn_classifier",
        ]
    }
    original_sys_path = list(sys.path)

    functions_framework = types.ModuleType("functions_framework")
    functions_framework.http = lambda fn: fn

    preview_module = types.ModuleType("vertexai.preview")
    preview_generative_models = types.ModuleType("vertexai.preview.generative_models")
    preview_module.generative_models = preview_generative_models

    vertexai_module = types.ModuleType("vertexai")
    vertexai_module.init = lambda *args, **kwargs: None
    vertexai_module.preview = preview_module

    generative_models_module = types.ModuleType("vertexai.generative_models")

    class Content:
        def __init__(self, role=None, parts=None):
            self.role = role
            self.parts = parts or []

    class Part:
        @staticmethod
        def from_text(text):
            return text

    class GenerativeModel:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    generative_models_module.Content = Content
    generative_models_module.GenerativeModel = GenerativeModel
    generative_models_module.Part = Part

    google_module = types.ModuleType("google")
    google_cloud_module = types.ModuleType("google.cloud")
    firestore_module = types.ModuleType("google.cloud.firestore")
    firestore_module.Client = object
    google_cloud_module.firestore = firestore_module
    google_module.cloud = google_cloud_module

    flask_module = types.ModuleType("flask")
    flask_module.jsonify = lambda payload: payload

    requests_module = types.ModuleType("requests")
    requests_module.get = lambda *args, **kwargs: None

    sys.modules["functions_framework"] = functions_framework
    sys.modules["vertexai"] = vertexai_module
    sys.modules["vertexai.preview"] = preview_module
    sys.modules["vertexai.preview.generative_models"] = preview_generative_models
    sys.modules["vertexai.generative_models"] = generative_models_module
    sys.modules["google"] = google_module
    sys.modules["google.cloud"] = google_cloud_module
    sys.modules["google.cloud.firestore"] = firestore_module
    sys.modules["flask"] = flask_module
    sys.modules["requests"] = requests_module

    for local_module_name in ("banking_playbooks", "rag_retriever", "turn_classifier"):
        sys.modules.pop(local_module_name, None)

    sys.path.insert(0, str(path.parent))
    try:
        return load_module(name, path)
    finally:
        sys.path[:] = original_sys_path
        for module_name, original_module in original_modules.items():
            if original_module is None:
                sys.modules.pop(module_name, None)
            else:
                sys.modules[module_name] = original_module


class ChatbotTurnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.turn_modules = [
            load_module("empathetic_turn_classifier", EMPATHETIC_BACKEND / "turn_classifier.py"),
            load_module("nonempathetic_turn_classifier", NONEMPATHETIC_BACKEND / "turn_classifier.py"),
        ]
        cls.playbook_modules = [
            load_module("empathetic_playbooks", EMPATHETIC_BACKEND / "banking_playbooks.py"),
            load_module("nonempathetic_playbooks", NONEMPATHETIC_BACKEND / "banking_playbooks.py"),
        ]
        cls.rag_modules = [
            load_rag_module("empathetic_rag", EMPATHETIC_BACKEND / "rag_retriever.py"),
            load_rag_module("nonempathetic_rag", NONEMPATHETIC_BACKEND / "rag_retriever.py"),
        ]
        cls.main_modules = [
            load_backend_main("empathetic_main", EMPATHETIC_BACKEND / "main.py"),
            load_backend_main("nonempathetic_main", NONEMPATHETIC_BACKEND / "main.py"),
        ]

    def assert_turn_classification(self, question: str, expected: str):
        for module in self.turn_modules:
            self.assertEqual(module.classify_turn(question), expected, msg=f"{module.__name__}: {question!r}")

    def test_greeting_only_turn_stays_greeting(self):
        self.assert_turn_classification("hi", "greeting_only")
        self.assert_turn_classification("hello there", "greeting_only")

    def test_mixed_greeting_with_real_question_is_substantive(self):
        self.assert_turn_classification(
            "Hi i need to open up an account. Need some info on what docs i need to have on me?",
            "substantive",
        )

    def test_acknowledgement_plus_question_is_substantive(self):
        self.assert_turn_classification("Thanks, what is the annual fee?", "substantive")
        self.assert_turn_classification("Ok can you explain loan eligibility?", "substantive")

    def test_punctuation_only_turn_is_unclear(self):
        self.assert_turn_classification("???", "unclear")

    def test_colloquial_account_opening_matches_playbook(self):
        question = "Hi i need to open up an account. Need some info on what docs i need to have on me?"
        for module in self.playbook_modules:
            result = module.build_playbook_response(question)
            self.assertIsNotNone(result, msg=module.__name__)
            self.assertIn("proof of address", result.text.lower(), msg=module.__name__)

    def test_bring_and_paperwork_variants_match_playbook(self):
        variants = [
            "What paperwork do I need to open a bank account?",
            "What do I need to bring to open an account?",
        ]
        for question in variants:
            for module in self.playbook_modules:
                result = module.build_playbook_response(question)
                self.assertIsNotNone(result, msg=f"{module.__name__}: {question!r}")
                self.assertIn("identification", result.text.lower(), msg=f"{module.__name__}: {question!r}")

    def test_negative_balance_question_now_hits_playbook(self):
        question = "Hi there, what happens if my account balance goes negative?"
        for module in self.playbook_modules:
            result = module.build_playbook_response(question)
            self.assertIsNotNone(result, msg=module.__name__)
            self.assertIn("negative", result.text.lower(), msg=module.__name__)
            self.assertIn("overdraft", result.text.lower(), msg=module.__name__)

    def test_annual_fee_and_service_hours_use_subject_specific_live_fallbacks(self):
        cases = [
            ("Thanks, what is the annual fee?", "annual fee"),
            ("Hello team, what are your customer service hours?", "customer service hours"),
        ]
        for question, marker in cases:
            for module in self.playbook_modules:
                result = module.build_playbook_response(question)
                self.assertIsNotNone(result, msg=f"{module.__name__}: {question!r}")
                self.assertEqual(result.response_mode, "live-fallback", msg=f"{module.__name__}: {question!r}")
                self.assertIn(marker, result.text.lower(), msg=f"{module.__name__}: {question!r}")

    def test_international_transfer_question_now_hits_playbook(self):
        question = "Ok, can I transfer money internationally?"
        for module in self.playbook_modules:
            result = module.build_playbook_response(question)
            self.assertIsNotNone(result, msg=module.__name__)
            self.assertIn("international transfer", result.text.lower(), msg=module.__name__)
            self.assertTrue(
                any(marker in result.text.lower() for marker in ("swift", "bic", "iban")),
                msg=module.__name__,
            )

    def test_security_incident_questions_hit_playbook(self):
        cases = {
            "What should I do if my phone with the banking app is stolen?": "stolen",
            "Can I freeze my account temporarily?": "temporary",
            "How can I contact customer support quickly?": "fastest support path",
        }
        for question, expected_marker in cases.items():
            for module in self.playbook_modules:
                result = module.build_playbook_response(question)
                self.assertIsNotNone(result, msg=f"{module.__name__}: {question!r}")
                self.assertIn(expected_marker, result.text.lower(), msg=f"{module.__name__}: {question!r}")

    def test_card_overview_playbook_has_no_invented_product_families(self):
        forbidden_markers = ["essential card", "rewards card", "travel card", "elite card"]
        question = "What credit cards do you offer?"
        for module in self.playbook_modules:
            result = module.build_playbook_response(question)
            self.assertIsNotNone(result, msg=module.__name__)
            lowered = result.text.lower()
            for marker in forbidden_markers:
                self.assertNotIn(marker, lowered, msg=f"{module.__name__}: found {marker!r}")

    def test_remaining_failure_clusters_now_have_specific_playbooks(self):
        cases = {
            "Which credit card is best for cashback?": "cashback",
            "What types of loans do you offer?": "personal borrowing",
            "How do I know how much house I can afford?": "monthly income",
            "How much emergency savings should I aim for?": "3 to 6 months",
            "How do I recognize phishing messages pretending to be from the bank?": "otp",
        }
        for question, marker in cases.items():
            for module in self.playbook_modules:
                result = module.build_playbook_response(question)
                self.assertIsNotNone(result, msg=f"{module.__name__}: {question!r}")
                self.assertIn(marker, result.text.lower(), msg=f"{module.__name__}: {question!r}")

    def test_transfer_fee_and_limit_questions_use_subject_specific_live_fallbacks(self):
        cases = [
            ("Are there transfer fees for sending money?", "transfer fee"),
            ("Is there a daily transfer limit?", "transfer limit"),
        ]
        for question, marker in cases:
            for module in self.playbook_modules:
                result = module.build_playbook_response(question)
                self.assertIsNotNone(result, msg=f"{module.__name__}: {question!r}")
                self.assertEqual(result.response_mode, "live-fallback", msg=f"{module.__name__}: {question!r}")
                self.assertIn(marker, result.text.lower(), msg=f"{module.__name__}: {question!r}")

    def test_weekend_support_answer_stays_cautious(self):
        question = "Do you offer support on weekends?"
        for module in self.playbook_modules:
            result = module.build_playbook_response(question)
            self.assertIsNotNone(result, msg=module.__name__)
            self.assertEqual(result.response_mode, "live-fallback", msg=module.__name__)
            lowered = result.text.lower()
            self.assertIn("weekend", lowered, msg=module.__name__)
            self.assertIn("self-service", lowered, msg=module.__name__)
            self.assertIn("cannot verify staffed weekend support", lowered, msg=module.__name__)

    def test_english_queries_gain_vietnamese_official_rag_hints(self):
        question = "What documents do I need to open an account?"
        for module in self.rag_modules:
            queries = module._expand_queries(question)
            joined = " | ".join(queries).lower()
            self.assertNotIn("techcombank", joined, msg=module.__name__)
            self.assertTrue(
                any("mở tài khoản" in query.lower() or "hồ sơ mở tài khoản" in query.lower() for query in queries),
                msg=f"{module.__name__}: missing Vietnamese account-opening hints",
            )

    def test_rag_queries_expand_for_hours_and_international_transfer(self):
        cases = {
            "Hello team, what are your customer service hours?": "giờ hỗ trợ khách hàng",
            "Ok, can I transfer money internationally?": "chuyển tiền quốc tế",
        }
        for question, expected_hint in cases.items():
            for module in self.rag_modules:
                queries = module._expand_queries(question)
                self.assertTrue(
                    any(expected_hint in query.lower() for query in queries),
                    msg=f"{module.__name__}: missing hint {expected_hint!r} for {question!r}",
                )

    def test_cache_validation_rejects_generic_strict_fallbacks(self):
        cases = [
            "Thanks, what is the annual fee?",
            "Good morning, what are your current mortgage rates?",
            "Hello team, what are your customer service hours?",
        ]
        for question in cases:
            for module in self.main_modules:
                generic_fallback = module.finalize_response(
                    module.LIVE_VERIFICATION_FALLBACK,
                    question,
                    rag_used=False,
                    response_mode="live-fallback",
                )
                subject_fallback = module.finalize_response(
                    module.build_live_verification_fallback(question),
                    question,
                    rag_used=False,
                    response_mode="live-fallback",
                )
                self.assertFalse(
                    module.is_bad_cached_response(
                        subject_fallback,
                        question,
                        response_mode="live-fallback",
                        grounding_scope="live_fallback",
                        rag_used=False,
                    ),
                    msg=f"{module.__name__}: should accept subject-aware fallback for {question!r}",
                )
                generic_is_bad = module.is_bad_cached_response(
                    generic_fallback,
                    question,
                    response_mode="live-fallback",
                    grounding_scope="live_fallback",
                    rag_used=False,
                )
                if generic_fallback == subject_fallback:
                    self.assertFalse(
                        generic_is_bad,
                        msg=f"{module.__name__}: finalized generic fallback already repairs to the subject-aware form for {question!r}",
                    )
                else:
                    self.assertTrue(
                        generic_is_bad,
                        msg=f"{module.__name__}: should reject stale generic fallback for {question!r}",
                    )

    def test_cache_validation_rejects_model_only_for_playbook_questions(self):
        question = "Hi there, what happens if my account balance goes negative?"
        for module in self.main_modules:
            stale_generated = module.finalize_response(
                "A negative account balance typically means you've spent more than you have available, leading to an overdraft.",
                question,
                rag_used=False,
                response_mode="generated",
            )
            self.assertTrue(
                module.is_bad_cached_response(
                    stale_generated,
                    question,
                    response_mode="generated",
                    grounding_scope="model_only",
                    rag_used=False,
                ),
                msg=f"{module.__name__}: should reject model_only cache hit for playbook question",
            )

    def test_nonmale_service_overview_detection_is_not_overbroad(self):
        nonmale_main = self.main_modules[1]
        self.assertFalse(nonmale_main.is_service_overview_question("Hi there, what happens if my account balance goes negative?"))
        self.assertFalse(nonmale_main.is_service_overview_question("Ok, can I transfer money internationally?"))
        self.assertFalse(nonmale_main.is_service_overview_question("Which credit card is best for travel?"))
        self.assertTrue(nonmale_main.is_service_overview_question("Can you compare options for card products?"))

    def test_strict_grounding_does_not_hijack_security_or_contact_flow(self):
        cases = [
            "What should I do if my phone with the banking app is stolen?",
            "How can I contact customer support quickly?",
        ]
        for question in cases:
            for module in self.main_modules:
                self.assertFalse(module.needs_strict_grounding(question), msg=f"{module.__name__}: {question!r}")

    def test_general_how_much_guidance_questions_are_not_forced_into_strict_grounding(self):
        cases = [
            "How do I know how much house I can afford?",
            "How much emergency savings should I aim for?",
        ]
        for question in cases:
            for module in self.main_modules:
                self.assertFalse(module.needs_strict_grounding(question), msg=f"{module.__name__}: {question!r}")

    def test_nonmale_finalize_preserves_specific_playbook_live_fallbacks(self):
        nonmale_main = self.main_modules[1]
        nonmale_playbooks = self.playbook_modules[1]
        question = "What is the interest rate on your basic savings account?"
        playbook = nonmale_playbooks.build_playbook_response(question)
        self.assertIsNotNone(playbook)
        self.assertEqual(playbook.response_mode, "live-fallback")
        finalized = nonmale_main.finalize_response(
            playbook.text,
            question,
            rag_used=False,
            response_mode=playbook.response_mode,
        )
        self.assertIn("savings rate", finalized.lower())
        self.assertIn("product type", finalized.lower())


if __name__ == "__main__":
    unittest.main()
