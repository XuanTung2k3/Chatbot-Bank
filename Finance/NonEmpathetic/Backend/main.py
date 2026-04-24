import datetime
import hashlib
import json
import os
import re
import uuid
from http import HTTPStatus
from typing import List, Optional

import functions_framework
import vertexai.preview.generative_models as generative_models
from banking_playbooks import PlaybookResult, build_playbook_response
from flask import jsonify
from google.cloud import firestore
from rag_retriever import retrieve_context, should_retrieve
from turn_classifier import classify_turn as classify_social_turn, normalize_turn
from vertexai.generative_models import Content, GenerativeModel, Part

# --------------------------------------------------------------------------------------------------------------------------------

PROJECT_ID = "gen-lang-client-0975766004"
CHATBOT_TYPE = "amazingbank-non-empathetic-rag"
GLOBAL_CACHE_COLLECTION = "GlobalQuestionAnswerCacheFinanceNonEmpathetic"
CACHE_VERSION = "v11"
MAX_RESPONSE_WORDS = 120
MIN_DETAILED_RESPONSE_WORDS = 80
RAG_MAX_SOURCES = 5
PUBLIC_BANK_NAME = os.getenv("PUBLIC_BANK_NAME", "AmazingBank").strip() or "AmazingBank"
SOURCE_BANK_NAME = os.getenv("SOURCE_BANK_NAME", "").strip()
SOURCE_BANK_SHORT_NAME = os.getenv("SOURCE_BANK_SHORT_NAME", "").strip()

FIXED_OPENING_MESSAGE = (
    "Hello and welcome. I am your financial advisor at AmazingBank.\n\n"
    "I can provide information about bank services, products, and financial questions. "
    "How can I assist you today."
)

LIVE_VERIFICATION_FALLBACK = (
    "I cannot verify an exact live AmazingBank figure in this chat, so I will not guess. "
    "Use the official AmazingBank support channel for the latest posted detail, and I can still help you compare the right options and questions to check."
)

GENERAL_SUPPORT_FALLBACK = (
    "I can give direct practical next steps if you provide the exact goal, amount or budget, and timeline. "
    "For exact AmazingBank-only details, use the official AmazingBank support channel."
)

SERVICE_REPLACEMENTS = {
    r"\bF@st\s*Mobile\b": "AmazingBank Mobile App",
    r"\bFast\s*Mobile\b": "AmazingBank Mobile App",
    r"\bF@st\s*e?Bank(?:ing)?\b": "AmazingBank Online Banking",
    r"\bFast\s*e?Bank(?:ing)?\b": "AmazingBank Online Banking",
    r"\bTCBS\b": "AmazingBank Investment Platform",
    r"\bAmazing\s+Bank\b": "AmazingBank",
}

OTHER_BANK_PATTERNS = [
    r"\bVietcombank\b",
    r"\bVPBank\b",
    r"\bBIDV\b",
    r"\bMB\s*Bank\b",
    r"\bMBBank\b",
    r"\bAgribank\b",
    r"\bACB\b",
    r"\bSacombank\b",
    r"\bTPBank\b",
]

STRICT_FACT_PATTERNS = [
    r"\btoday\b",
    r"\blatest\b",
    r"\blive\b",
    r"\bsavings rates?\b",
    r"\binterest rates?\b",
    r"\binterest rate on (?:your )?basic savings account\b",
    r"\bmortgage rates?\b",
    r"\blãi suất\b",
    r"\bannual fee\b",
    r"\bphí\b",
    r"\bapr\b",
    r"\btransfer fees?\b",
    r"\bdaily transfer limit\b",
    r"\bmonthly transfer limit\b",
    r"\bmonthly account fees?\b",
    r"\batm withdrawals? free\b",
    r"\batm withdrawal fees?\b",
    r"\bsupport hours?\b",
    r"\bservice hours?\b",
    r"\bcontact hours?\b",
    r"\bbusiness hours?\b",
    r"\bweekend support\b",
    r"\bsupport on weekends?\b",
    r"\boffer support on weekends?\b",
    r"\bweekend hours?\b",
    r"\bopen on weekends?\b",
    r"\bexact\b",
    r"\bcurrent\b",
    r"\bupdated\b",
    r"\bprocessing time\b",
    r"\bwithin\s+\d+",
    r"\d+\s*%",
]

NON_EMPATHETIC_REPLACEMENTS = [
    (r"\bI hear you(?:,)?\b", ""),
    (r"\bI understand(?: this matters to you| this is important)?(?:,)?\b", ""),
    (r"\bI know this is important for you(?:,)?\b", ""),
    (r"\bI am sorry(?:,)?\b", ""),
    (r"\bI'm sorry(?:,)?\b", ""),
    (r"\byou are not alone(?:,)?\b", ""),
    (r"\bwe(?:'| a)ll get through this together(?:,)?\b", ""),
    (r"\bGreat question(?:,)?\b", ""),
    (r"\bThanks for (?:the question|sharing)(?:,)?\b", ""),
    (r"\bHappy to help(?:,)?\b", ""),
]

FINANCE_DETAIL_SUFFIXES = {
    "cards": (
        "Compare monthly spending categories, cashback or travel value, installment needs, annual-fee tier, "
        "and card controls in AmazingBank Mobile App."
    ),
    "loans": (
        "Prepare income proof, repayment budget, requested amount, collateral if relevant, and complete documents "
        "before using AmazingBank Mobile App or a branch."
    ),
    "savings": (
        "Compare term length, withdrawal flexibility, expected rate conditions, and branch or AmazingBank Online "
        "Banking management."
    ),
    "digital": (
        "Check transfer needs, bill payment, alerts, card controls, device security, and OTP protection before "
        "choosing the setup."
    ),
    "investment": (
        "Define time horizon, risk level, liquidity need, and whether savings, funds, or bonds fit the goal."
    ),
}

DIRECT_NEXT_STEP_PROMPTS = [
    "Provide your goal, budget, and timeline for a targeted recommendation.",
    "Provide the exact product purpose and constraints to receive a precise option.",
    "Provide your preferred channel and expected timeline for a concrete action plan.",
]

ACKNOWLEDGEMENT_RESPONSE = "Acknowledged. I can assist with AmazingBank services again when needed."

UNCLEAR_INPUT_RESPONSE = "Please provide the AmazingBank service or goal you want help with."

ACKNOWLEDGEMENT_PATTERNS = [
    r"^(ok|okay|thanks|thank you|thx|ty|got it|understood|that'?s all|that is all|bye|goodbye)\b",
    r"^(cảm ơn|cam on|xong rồi|tạm biệt)\b",
]

GREETING_RESPONSE = "Hello. Provide an AmazingBank service or question to continue."

GREETING_PATTERNS = [
    r"^(hi|hello|hey|good morning|good afternoon|good evening)\b",
    r"^(xin chào|chào)\b",
]

SERVICE_OVERVIEW_KEYWORDS = [
    "service", "services", "product", "products", "loan", "loans", "card", "cards",
    "savings", "saving", "account", "app", "online banking", "mobile banking",
    "investment", "transfer", "payment", "feature", "benefit",
    "dịch vụ", "sản phẩm", "vay", "thẻ", "tiết kiệm", "tài khoản", "ứng dụng",
]

SERVICE_OVERVIEW_SIGNALS = [
    "what products do you offer",
    "what services do you offer",
    "what credit cards do you offer",
    "what types of loans do you offer",
    "tell me about",
    "overview",
    "difference between",
    "compare options",
]

FINANCE_FACTUAL_CATALOG = {
    "cards": (
        "AmazingBank card services generally include debit and credit categories. "
        "Core comparison points are spending pattern, benefit type, installment eligibility, annual-fee tier, "
        "and spending controls in AmazingBank Mobile App."
    ),
    "loans": (
        "AmazingBank loan options are typically grouped by purpose, such as personal, home, auto, and business borrowing. "
        "Application channels are AmazingBank Mobile App or branch. Core review factors are income proof, repayment "
        "capacity, requested amount, affordability, and complete documents."
    ),
    "savings": (
        "AmazingBank savings options include flexible and term deposits. Practical comparison points are term length, "
        "rate conditions, withdrawal flexibility, and digital management in AmazingBank Online Banking."
    ),
    "digital": (
        "AmazingBank digital services include AmazingBank Mobile App and AmazingBank Online Banking. "
        "Core capabilities are transfers, bill payment, card controls, account tracking, alerts, and security settings."
    ),
    "investment": (
        "AmazingBank Investment Platform supports fund and bond access alongside savings planning. "
        "Core planning factors are goal horizon, risk preference, liquidity need, and expected return range."
    ),
}

INTENT_KEYWORDS = {
    "cards": ["card", "cards", "credit", "debit", "visa", "mastercard", "thẻ", "the", "tin dung", "mo the"],
    "loans": ["loan", "loans", "mortgage", "vay", "installment", "trả góp", "tra gop", "lonnn"],
    "savings": ["saving", "savings", "deposit", "term", "tiết kiệm", "tiet kiem", "gửi", "gui"],
    "digital": ["app", "online banking", "mobile banking", "ebanking", "f@st"],
    "investment": ["invest", "investment", "fund", "bond", "portfolio"],
}

SERVICE_DETAIL_SUFFIX_KEY = "compare monthly spending categories"

SEMANTIC_STOPWORDS = {
    "the", "a", "an", "and", "or", "for", "to", "of", "in", "on", "with", "about", "how", "what", "which",
    "can", "i", "me", "my", "you", "your", "amazingbank", "official", "support", "channel", "latest", "current",
    "exact", "live", "posted", "detail", "details", "number", "please", "check", "help", "still", "today",
}

QUESTION_FOCUS_PHRASES = {
    "annual_fee": ("annual fee", "annual fees", "card annual fee", "credit card fee", "debit card fee"),
    "savings_rate": ("savings rate", "interest rate on your basic savings account", "interest rate on savings"),
    "mortgage_rate": ("mortgage rate", "mortgage rates", "home loan rate", "30-year fixed", "30 year fixed"),
    "transfer_fee": ("transfer fees", "transfer fee", "fees for sending money"),
    "transfer_limit": ("daily transfer limit", "monthly transfer limit", "transfer limit"),
    "monthly_account_fee": ("monthly account fee", "monthly account fees", "charge monthly account fees"),
    "atm_fee": ("atm withdrawals free", "atm withdrawal free", "atm withdrawal fee", "atm withdrawal fees"),
    "service_hours": ("customer service hours", "support hours", "service hours", "contact hours", "business hours", "weekend support", "support on weekends", "offer support on weekends", "weekend hours", "open on weekends"),
    "negative_balance": ("negative balance", "balance goes negative", "account goes negative", "below zero", "overdraft", "insufficient funds", "overdrawn"),
    "international_transfer": ("international transfer", "transfer money internationally", "transfer internationally", "send money abroad", "send money overseas", "wire internationally", "international wire", "swift", "bic", "iban"),
}

QUESTION_RESPONSE_MARKERS = {
    "annual_fee": ("annual fee", "fee schedule", "card fee", "credit card", "debit card"),
    "savings_rate": ("savings rate", "interest", "balance tier", "fixed term", "flexible access"),
    "mortgage_rate": ("mortgage", "home loan", "rate", "30-year fixed"),
    "transfer_fee": ("transfer fee", "fee schedule", "domestic", "international", "currency", "urgent"),
    "transfer_limit": ("transfer limit", "daily", "monthly", "verification", "security"),
    "monthly_account_fee": ("monthly account fee", "monthly fee", "fee schedule", "waiver"),
    "atm_fee": ("atm", "withdrawal", "fee schedule", "in-network", "third-party"),
    "service_hours": ("customer service hours", "support hours", "hours", "contact page", "branch listing", "weekend", "self-service"),
    "negative_balance": ("negative balance", "overdraft", "available balance", "low-balance", "overdrawn"),
    "international_transfer": ("international transfer", "swift", "bic", "iban", "destination country", "exchange rate", "supported destinations"),
}

CRITICAL_CACHE_PATTERNS = [
    "credit card",
    "debit card",
    "loan",
    "mortgage",
    "transfer",
    "support",
    "fraud",
    "security",
    "stolen phone",
    "lost card",
]

EMOJI_PATTERN = re.compile(
    "[" "\U0001F300-\U0001FAFF" "\U00002600-\U000027BF" "\U0001F1E6-\U0001F1FF" "]+",
    flags=re.UNICODE,
)

BLOCKED_OUTPUT_PATTERNS = [
    r"could not process",
    r"process that request",
    r"i hear you,\s*and i could not",
    r"i could not process",
]

UNCLEAR_INPUT_PATTERNS = [
    r"^[?.!\s]+$",
    r"\blonnn\b",
    r"\bpls\b",
]

PROMPT_INJECTION_PATTERNS = [
    r"ignore previous",
    r"hidden prompt",
    r"system prompt",
    r"reveal .*rules",
    r"remove sanit",
]

# --------------------------------------------------------------------------------------------------------------------------------


def init_firestore_client() -> firestore.Client:
    """Initialize and return a Firestore client."""
    return firestore.Client(project=PROJECT_ID)


# --------------------------------------------------------------------------------------------------------------------------------


def normalize_question(question: str) -> str:
    """Normalize user question text for stable cache keys."""
    return normalize_turn(question)


# --------------------------------------------------------------------------------------------------------------------------------


def normalize_intent_text(question: str) -> str:
    """Normalize common typo and romanized Vietnamese intent text before matching."""
    normalized = normalize_question(question)
    replacements = {
        "lonnn": "loan",
        "tin dung": "credit",
        "the tin dung": "credit card",
        "mo the": "card",
        "mở thẻ": "card",
        "tra gop": "installment",
        "tiet kiem": "savings",
        "gui tiet kiem": "savings",
    }
    for source, target in replacements.items():
        normalized = re.sub(rf"\b{re.escape(source)}\b", target, normalized, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", normalized).strip()


# --------------------------------------------------------------------------------------------------------------------------------


def get_question_hash(normalized_question: str) -> str:
    """Create a deterministic hash for normalized question text."""
    return hashlib.sha256(normalized_question.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------------------------------------------------------------


def trim_to_word_limit(text: str, max_words: int = MAX_RESPONSE_WORDS) -> str:
    """Hard-enforce maximum word count."""
    words = (text or "").split()
    if len(words) <= max_words:
        return (text or "").strip()

    trimmed = " ".join(words[:max_words]).rstrip(" ,;:-")
    if trimmed and trimmed[-1] not in ".!?":
        trimmed += "..."
    return trimmed


# --------------------------------------------------------------------------------------------------------------------------------


def _source_bank_name_patterns() -> List[str]:
    patterns = []
    if SOURCE_BANK_NAME:
        patterns.append(rf"\b{re.escape(SOURCE_BANK_NAME)}\b")
        patterns.append(rf"\b{re.escape(SOURCE_BANK_NAME)}\s+Mobile\b")
        patterns.append(rf"\b{re.escape(SOURCE_BANK_NAME)}\s+(?:Online\s+Banking|eBanking)\b")
    if SOURCE_BANK_SHORT_NAME:
        patterns.append(rf"\b{re.escape(SOURCE_BANK_SHORT_NAME)}\b")
        patterns.append(rf"\b{re.escape(SOURCE_BANK_SHORT_NAME)}\s+mobile\b")
    return patterns


def _replace_source_bank_branding(text: str) -> str:
    content = text
    if SOURCE_BANK_NAME:
        content = re.sub(rf"\b{re.escape(SOURCE_BANK_NAME)}\s+Mobile\b", f"{PUBLIC_BANK_NAME} Mobile App", content, flags=re.IGNORECASE)
        content = re.sub(rf"\b{re.escape(SOURCE_BANK_NAME)}\s+(?:Online\s+Banking|eBanking)\b", f"{PUBLIC_BANK_NAME} Online Banking", content, flags=re.IGNORECASE)
    if SOURCE_BANK_SHORT_NAME:
        content = re.sub(rf"\b{re.escape(SOURCE_BANK_SHORT_NAME)}\s+mobile\b", f"{PUBLIC_BANK_NAME} Mobile App", content, flags=re.IGNORECASE)
    for pattern in _source_bank_name_patterns():
        content = re.sub(pattern, PUBLIC_BANK_NAME, content, flags=re.IGNORECASE)
    return content


# --------------------------------------------------------------------------------------------------------------------------------


def sanitize_bank_and_service_terms(text: str) -> str:
    """Ensure output contains only AmazingBank branding and generic service names."""
    sanitized = (text or "").strip()
    if not sanitized:
        return ""

    for pattern, replacement in SERVICE_REPLACEMENTS.items():
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

    sanitized = _replace_source_bank_branding(sanitized)

    # Remove real-world hotline numbers from final output.
    sanitized = re.sub(
        r"\b(?:\+?84[\s\-.]?)?(?:1800|1900)[\s\-.]?\d{3}[\s\-.]?\d{3}\b",
        "official AmazingBank support channel",
        sanitized,
        flags=re.IGNORECASE,
    )
    sanitized = re.sub(
        r"\b1800[\s\-.]*588[\s\-.]*822\b",
        "official AmazingBank support channel",
        sanitized,
        flags=re.IGNORECASE,
    )

    # Replace all non-target banks with a generic phrase.
    for pattern in OTHER_BANK_PATTERNS:
        sanitized = re.sub(pattern, "other banks", sanitized, flags=re.IGNORECASE)

    # Clean duplicated tokens.
    sanitized = re.sub(r"\bother banks\b(?:\s*,\s*\bother banks\b)+", "other banks", sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    return sanitized


# --------------------------------------------------------------------------------------------------------------------------------


def needs_strict_grounding(question: str) -> bool:
    """Detect whether the query asks for exact live facts that require verified grounding."""
    question_lower = normalize_intent_text(question)
    return any(re.search(pattern, question_lower, flags=re.IGNORECASE) for pattern in STRICT_FACT_PATTERNS)


# --------------------------------------------------------------------------------------------------------------------------------


def is_service_overview_question(question: str) -> bool:
    """Detect broad product/service intent so retrieval can enrich answers."""
    question_lower = normalize_intent_text(question)
    if needs_strict_grounding(question) or build_playbook_response(question) is not None:
        return False
    intent = detect_finance_intent(question)
    if not intent:
        return False
    has_overview_signal = any(keyword in question_lower for keyword in SERVICE_OVERVIEW_SIGNALS)
    has_overview_keyword = any(keyword in question_lower for keyword in SERVICE_OVERVIEW_KEYWORDS)
    return has_overview_signal and has_overview_keyword


# --------------------------------------------------------------------------------------------------------------------------------


def is_acknowledgement_or_closer(question: str) -> bool:
    """Detect short closers that should not trigger direct next-step prompts."""
    return get_turn_classification(question) == "ack_only"


# --------------------------------------------------------------------------------------------------------------------------------


def is_greeting(question: str) -> bool:
    """Detect simple greetings after an initialized session."""
    return get_turn_classification(question) == "greeting_only"


# --------------------------------------------------------------------------------------------------------------------------------


def detect_finance_intent(question: str) -> str:
    """Infer the primary finance intent for factual-core alignment."""
    question_lower = normalize_intent_text(question)
    for intent, keywords in INTENT_KEYWORDS.items():
        if any(keyword in question_lower for keyword in keywords):
            return intent
    return ""


# --------------------------------------------------------------------------------------------------------------------------------


def _semantic_tokens(text: str) -> set:
    normalized = normalize_intent_text(text)
    return {
        token
        for token in re.findall(r"[a-z0-9]+", normalized)
        if len(token) > 1 and token not in SEMANTIC_STOPWORDS
    }


# --------------------------------------------------------------------------------------------------------------------------------


def response_relevance_score(question: str, text: str) -> float:
    question_tokens = _semantic_tokens(question)
    if not question_tokens:
        return 0.0
    response_tokens = _semantic_tokens(text)
    return len(question_tokens & response_tokens) / max(1, len(question_tokens))


# --------------------------------------------------------------------------------------------------------------------------------


def classify_question_focus(question: str) -> str:
    normalized = normalize_intent_text(question)
    for focus, phrases in QUESTION_FOCUS_PHRASES.items():
        if any(phrase in normalized for phrase in phrases):
            return focus
    return ""


# --------------------------------------------------------------------------------------------------------------------------------


def response_has_subject_alignment(text: str, question: str) -> bool:
    content = sanitize_bank_and_service_terms(text).lower()
    focus = classify_question_focus(question)
    markers = QUESTION_RESPONSE_MARKERS.get(focus, ())
    if markers and any(marker in content for marker in markers):
        return True

    if focus or build_playbook_response(question) is not None or needs_strict_grounding(question):
        return response_relevance_score(question, content) >= 0.18

    return True


# --------------------------------------------------------------------------------------------------------------------------------


def is_critical_cache_intent(question: str) -> bool:
    normalized = normalize_intent_text(question)
    return any(pattern in normalized for pattern in CRITICAL_CACHE_PATTERNS)


# --------------------------------------------------------------------------------------------------------------------------------


def is_generic_low_value_response(text: str, question: str) -> bool:
    content = sanitize_bank_and_service_terms(text).strip().lower()
    if not content:
        return True

    generic_markers = [
        "official amazingbank support channel",
        "i can explain the practical steps and decision points here",
        "exact amazingbank-only details",
    ]
    has_generic_marker = any(marker in content for marker in generic_markers)
    if not has_generic_marker:
        return False

    if classify_question_focus(question):
        return True

    return response_relevance_score(question, content) < 0.30


# --------------------------------------------------------------------------------------------------------------------------------


def cache_mode_matches_question(question: str, response_mode: str, grounding_scope: str, rag_used: bool) -> bool:
    playbook = build_playbook_response(question)
    if playbook is not None:
        if rag_used or grounding_scope == "official_rag":
            return True
        return response_mode == playbook.response_mode

    if needs_strict_grounding(question):
        return rag_used or grounding_scope == "official_rag" or response_mode == "live-fallback"

    return True


# --------------------------------------------------------------------------------------------------------------------------------


def build_live_verification_fallback(question: str) -> str:
    focus = classify_question_focus(question)

    if focus == "annual_fee":
        return (
            "I cannot verify the exact AmazingBank annual fee in this chat, and the amount can vary by card type and tier. "
            "Use the official AmazingBank fee schedule or the specific card page for the latest posted annual fee. I can still help compare the right fee questions and card tradeoffs."
        )

    if focus == "savings_rate":
        return (
            "I cannot verify the current AmazingBank savings rate in this chat, and the exact rate can depend on product type, balance tier, term, and channel. "
            "Use the official AmazingBank savings page or support channel for the latest posted rate. I can still help compare flexible-access and fixed-term savings questions."
        )

    if focus == "mortgage_rate":
        return (
            "I cannot verify the current AmazingBank mortgage rate in this chat, and the final rate can vary by product, borrower profile, and loan structure. "
            "Use the official AmazingBank mortgage or home-loan page for the latest posted rate. I can still help compare affordability points and the key rate questions to ask."
        )

    if focus == "transfer_fee":
        return (
            "I cannot verify the exact AmazingBank transfer fee in this chat. Pricing can depend on domestic versus international routing, channel, currency, urgency, and your account package. "
            "Use the official AmazingBank fee schedule or support channel for the latest posted transfer fee."
        )

    if focus == "transfer_limit":
        return (
            "I cannot verify the exact AmazingBank transfer limit in this chat. Limits can depend on channel, verification status, destination, and security settings. "
            "Use the official AmazingBank limits information or support channel for the current posted transfer limit on your profile."
        )

    if focus == "monthly_account_fee":
        return (
            "I cannot verify the exact AmazingBank monthly account fee in this chat, and the amount can vary by account type, package, and waiver conditions. "
            "Use the official AmazingBank fee schedule or support channel for the latest posted monthly account fee."
        )

    if focus == "atm_fee":
        return (
            "I cannot verify the exact AmazingBank ATM withdrawal fee in this chat. Fee treatment can depend on your card type, the ATM network, and whether the withdrawal is domestic or international. "
            "Use the official AmazingBank fee schedule or support channel for the latest posted ATM policy."
        )

    if focus == "service_hours":
        if "weekend" in normalize_intent_text(question):
            return (
                "AmazingBank Mobile App and AmazingBank Online Banking may still be available for self-service at any time, but I cannot verify staffed weekend support in this chat. "
                "Use the official AmazingBank contact page or support channel for the latest weekend hours for phone, chat, or branch assistance."
            )
        return (
            "I cannot verify the exact AmazingBank customer service hours in this chat because they can vary by channel, branch, and day. "
            "Use the official AmazingBank contact page, Mobile App, Online Banking, or branch listing for the latest hours. I can still help identify the fastest support path."
        )

    return LIVE_VERIFICATION_FALLBACK


# --------------------------------------------------------------------------------------------------------------------------------


def build_finance_factual_core(question: str) -> str:
    """Return canonical factual core for product/service intents."""
    intent = detect_finance_intent(question)
    return FINANCE_FACTUAL_CATALOG.get(intent, "")


# --------------------------------------------------------------------------------------------------------------------------------


def build_finance_detail_suffix(question: str) -> str:
    """Return intent-specific detail guidance instead of generic filler."""
    intent = detect_finance_intent(question)
    return FINANCE_DETAIL_SUFFIXES.get(intent, "")


# --------------------------------------------------------------------------------------------------------------------------------


def is_actionable_service_question(question: str) -> bool:
    """Return true only when direct next-step guidance is useful."""
    if (
        get_turn_classification(question) in {"ack_only", "greeting_only", "unclear", "empty"}
        or needs_strict_grounding(question)
        or build_playbook_response(question) is not None
    ):
        return False
    return is_service_overview_question(question)


# --------------------------------------------------------------------------------------------------------------------------------


def _is_short_non_actionable_input(question: str) -> bool:
    normalized = normalize_question(question)
    if not normalized:
        return False
    if (
        needs_strict_grounding(normalized)
        or is_unclear_or_prompt_attack(normalized)
        or build_playbook_response(normalized) is not None
        or detect_finance_intent(normalized)
        or is_service_overview_question(normalized)
    ):
        return False
    return len(normalized.split()) <= 2


# --------------------------------------------------------------------------------------------------------------------------------


def get_turn_classification(question: str) -> str:
    social_classification = classify_social_turn(question)
    if social_classification in {"empty", "greeting_only", "ack_only", "unclear"}:
        return social_classification

    if is_unclear_or_prompt_attack(question) or _is_short_non_actionable_input(question):
        return "unclear"

    return "substantive"


# --------------------------------------------------------------------------------------------------------------------------------


def is_unclear_short_input(question: str) -> bool:
    """Catch short non-actionable fragments without blocking one-word service intents."""
    return get_turn_classification(question) == "unclear"


# --------------------------------------------------------------------------------------------------------------------------------


def dedupe_repeated_sentences(text: str) -> str:
    """Remove duplicate sentence blocks caused by multi-pass post-processing."""
    content = (text or "").strip()
    if not content:
        return ""

    sentences = re.split(r"(?<=[.!?])\s+", content)
    seen = set()
    deduped = []
    for sentence in sentences:
        normalized = re.sub(r"\s+", " ", sentence.strip().lower())
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(sentence.strip())

    return " ".join(deduped).strip()


# --------------------------------------------------------------------------------------------------------------------------------


def has_duplicate_sentence(text: str) -> bool:
    """Detect repeated sentence blocks before serving cache hits."""
    content = (text or "").strip()
    if not content:
        return False

    sentences = re.split(r"(?<=[.!?])\s+", content)
    seen = set()
    for sentence in sentences:
        normalized = re.sub(r"\s+", " ", sentence.strip().lower())
        if not normalized:
            continue
        if normalized in seen:
            return True
        seen.add(normalized)
    return False


# --------------------------------------------------------------------------------------------------------------------------------


def contains_blocked_output(text: str) -> bool:
    """Detect stale frontend/model fallback text that must never reach users."""
    content = (text or "").lower()
    return any(re.search(pattern, content, flags=re.IGNORECASE) for pattern in BLOCKED_OUTPUT_PATTERNS)


# --------------------------------------------------------------------------------------------------------------------------------


def sanitize_blocked_output(text: str) -> str:
    """Replace stale bad fallback phrases with the verified-information fallback."""
    if contains_blocked_output(text):
        return GENERAL_SUPPORT_FALLBACK
    return text


# --------------------------------------------------------------------------------------------------------------------------------


def is_unclear_or_prompt_attack(question: str) -> bool:
    """Suppress next-step prompts for typo-heavy, unclear, or prompt-injection turns."""
    normalized = normalize_question(question)
    if any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in PROMPT_INJECTION_PATTERNS):
        return True
    return any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in UNCLEAR_INPUT_PATTERNS)


# --------------------------------------------------------------------------------------------------------------------------------


def response_meets_style_requirements(text: str, question: str) -> bool:
    """Validate non-empathetic cache hits before reuse."""
    content = (text or "").strip()
    if not content:
        return False
    lowered = content.lower()
    empathy_markers = ["i hear", "i understand", "happy to help", "thank you for sharing"]
    return not EMOJI_PATTERN.search(content) and not any(marker in lowered for marker in empathy_markers)


# --------------------------------------------------------------------------------------------------------------------------------


def is_bad_cached_response(
    text: str,
    question: str,
    response_mode: str = "generated",
    grounding_scope: str = "model_only",
    rag_used: bool = False,
) -> bool:
    """Reject stale cached responses with old bugs instead of serving them again."""
    return (
        not (text or "").strip()
        or contains_blocked_output(text)
        or has_duplicate_sentence(text)
        or not response_meets_style_requirements(text, question)
        or not cache_mode_matches_question(question, response_mode, grounding_scope, rag_used)
        or not response_has_subject_alignment(text, question)
        or (is_critical_cache_intent(question) and is_generic_low_value_response(text, question))
    )


# --------------------------------------------------------------------------------------------------------------------------------


def should_cache_response(
    response: str,
    question: str,
    response_mode: str,
    grounding_scope: str,
    rag_used: bool,
) -> bool:
    if not (response or "").strip():
        return False
    if response_mode in {"policy", "init"}:
        return False
    if is_bad_cached_response(response, question, response_mode, grounding_scope, rag_used):
        return False
    if is_critical_cache_intent(question) and response_mode == "generated" and not rag_used and grounding_scope == "model_only":
        return False
    return True


# --------------------------------------------------------------------------------------------------------------------------------


def ensure_factual_core_alignment(text: str, question: str) -> str:
    """Keep core factual content stable across empathetic and non-empathetic variants."""
    content = (text or "").strip()
    if not content or not is_service_overview_question(question):
        return content

    factual_core = build_finance_factual_core(question)
    if not factual_core:
        return content

    if len(content.split()) < 50:
        return f"{factual_core} {content}".strip()

    normalized_content = content.lower()
    strong_markers = [
        "debit",
        "credit",
        "personal loan",
        "home loan",
        "auto loan",
        "amazingbank mobile app",
        "amazingbank online banking",
        "amazingbank investment platform",
    ]
    if any(marker in normalized_content for marker in strong_markers):
        return content

    return f"{factual_core} {content}".strip()


# --------------------------------------------------------------------------------------------------------------------------------


def apply_direct_style(text: str, question: str) -> str:
    """Strengthen direct, action-oriented tone for non-empathetic mode."""
    content = (text or "").strip()
    if not content or content in {LIVE_VERIFICATION_FALLBACK, GENERAL_SUPPORT_FALLBACK}:
        return content

    # Strip residual conversational-soft patterns so style stays transactional.
    content = re.sub(r"\bif you want\b", "", content, flags=re.IGNORECASE)
    content = re.sub(r"\bif it helps\b", "", content, flags=re.IGNORECASE)
    content = re.sub(r"\bif needed\b", "", content, flags=re.IGNORECASE)
    content = re.sub(r"\blet us\b", "", content, flags=re.IGNORECASE)
    content = re.sub(r"\bwe can\b", "", content, flags=re.IGNORECASE)
    content = re.sub(r"\b[Tt]ell me your\b", "Provide your", content)
    content = re.sub(r"\b[Ss]hare your\b", "Provide your", content)
    content = re.sub(r"\band I (?:will|can) suggest\b", "for a targeted recommendation", content, flags=re.IGNORECASE)
    content = re.sub(r"\band I (?:will|can) help\b", "for a direct next-step plan", content, flags=re.IGNORECASE)
    content = re.sub(r"\s+", " ", content).strip()

    lowered = content.lower()
    if "next step:" in lowered:
        return content

    if not is_actionable_service_question(question):
        return content

    seed_source = normalize_question(question) or content.lower()
    seed = int(hashlib.sha256(seed_source.encode("utf-8")).hexdigest(), 16)
    prompt = DIRECT_NEXT_STEP_PROMPTS[seed % len(DIRECT_NEXT_STEP_PROMPTS)]
    return f"{content} Next step: {prompt}".strip()


# --------------------------------------------------------------------------------------------------------------------------------


def enforce_non_empathetic_tone(text: str) -> str:
    """Remove empathy markers and keep a neutral professional tone."""
    content = (text or "").strip()
    if not content:
        return ""

    for pattern, replacement in NON_EMPATHETIC_REPLACEMENTS:
        content = re.sub(pattern, replacement, content, flags=re.IGNORECASE)

    content = EMOJI_PATTERN.sub("", content)
    content = content.replace("!", ".")
    content = re.sub(r"\s+", " ", content).strip()
    content = re.sub(r"\.\.+", ".", content)
    content = re.sub(r"\s+\.", ".", content)
    content = re.sub(r"^[\s\.,;:!?-]+", "", content)
    content = re.sub(r"\s+([,;:])", r"\1", content)
    content = re.sub(r"([,;:])(?=\S)", r"\1 ", content)
    content = re.sub(r"\s+", " ", content).strip()

    if content and content[0].islower():
        content = content[0].upper() + content[1:]

    if not content:
        return GENERAL_SUPPORT_FALLBACK
    return content


# --------------------------------------------------------------------------------------------------------------------------------


def expand_service_depth_if_needed(text: str, question: str) -> str:
    """Expand short product/service replies with concrete guidance points."""
    content = (text or "").strip()
    if not content or content in {LIVE_VERIFICATION_FALLBACK, GENERAL_SUPPORT_FALLBACK}:
        return content

    if not is_actionable_service_question(question):
        return content

    if len(content.split()) >= MIN_DETAILED_RESPONSE_WORDS:
        return content

    suffix = build_finance_detail_suffix(question)
    if not suffix:
        return content

    if suffix.lower() in content.lower() or SERVICE_DETAIL_SUFFIX_KEY in content.lower():
        return content

    return f"{content} {suffix}".strip()


# --------------------------------------------------------------------------------------------------------------------------------


def determine_grounding_scope(response_mode: str, rag_used: bool, rag_scope: str = "", turn_classification: str = "substantive") -> str:
    if response_mode == "init":
        return "init"
    if response_mode == "playbook":
        return "playbook"
    if response_mode == "live-fallback":
        return "live_fallback"
    if response_mode == "policy" or turn_classification != "substantive":
        return "policy"
    if rag_used:
        return rag_scope or "official_rag"
    return "model_only"


# --------------------------------------------------------------------------------------------------------------------------------


def finalize_response(
    raw_response: str,
    question: str,
    rag_used: bool,
    response_mode: str = "generated",
    force_fallback: bool = False,
    turn_classification: Optional[str] = None,
) -> str:
    """Apply policy filters and constraints before returning a response."""
    response = sanitize_blocked_output((raw_response or "").strip())
    turn_classification = turn_classification or get_turn_classification(question)

    if turn_classification == "ack_only":
        return trim_to_word_limit(enforce_non_empathetic_tone(ACKNOWLEDGEMENT_RESPONSE))

    if turn_classification == "greeting_only":
        return trim_to_word_limit(enforce_non_empathetic_tone(GREETING_RESPONSE))

    if turn_classification == "unclear":
        return trim_to_word_limit(enforce_non_empathetic_tone(UNCLEAR_INPUT_RESPONSE))

    if force_fallback and not response:
        response = build_live_verification_fallback(question)
    elif not response:
        response = GENERAL_SUPPORT_FALLBACK

    if needs_strict_grounding(question) and not rag_used and response_mode == "generated":
        response = build_live_verification_fallback(question)
        response_mode = "live-fallback"

    response = sanitize_bank_and_service_terms(response)
    response = enforce_non_empathetic_tone(response)
    response = ensure_factual_core_alignment(response, question)
    response = expand_service_depth_if_needed(response, question)
    response = apply_direct_style(response, question)
    response = sanitize_bank_and_service_terms(response)
    response = sanitize_blocked_output(response)
    response = enforce_non_empathetic_tone(response)
    response = dedupe_repeated_sentences(response)
    response = trim_to_word_limit(response)
    return response


# --------------------------------------------------------------------------------------------------------------------------------


def get_cached_response(db: firestore.Client, normalized_question: str):
    """Read deterministic global response cache."""
    if not normalized_question:
        return None

    question_hash = get_question_hash(normalized_question)
    doc = db.collection(GLOBAL_CACHE_COLLECTION).document(question_hash).get()
    if not doc.exists:
        return None

    cached_data = doc.to_dict() or {}
    if cached_data.get("cacheVersion") != CACHE_VERSION:
        return None
    if cached_data.get("responseMode") == "policy":
        return None
    if not cached_data.get("response"):
        return None
    return cached_data


# --------------------------------------------------------------------------------------------------------------------------------


def save_cached_response(
    db: firestore.Client,
    normalized_question: str,
    response: str,
    rag_used: bool,
    response_mode: str,
    grounding_scope: str,
):
    """Persist deterministic global response cache."""
    if not normalized_question or not response:
        return

    question_hash = get_question_hash(normalized_question)
    now = datetime.datetime.now()

    cache_ref = db.collection(GLOBAL_CACHE_COLLECTION).document(question_hash)
    cache_ref.set(
        {
            "normalizedQuestion": normalized_question,
            "response": response,
            "ragUsed": rag_used,
            "responseMode": response_mode,
            "groundingScope": grounding_scope,
            "cacheVersion": CACHE_VERSION,
            "updatedAt": now,
        },
        merge=True,
    )


# --------------------------------------------------------------------------------------------------------------------------------


def response_from_chatbot(model, message, message_history):
    """
    Send a message to the chatbot and get a response.

    Args:
        model: The GenerativeModel instance
        message: The user's message string
        message_history: List of Content objects representing chat history

    Returns:
        Response text from model
    """
    chat = model.start_chat(history=message_history)
    model_response = chat.send_message(message)
    text = getattr(model_response, "text", None)
    if not text:
        raise ValueError("Empty model response text")
    return text


# --------------------------------------------------------------------------------------------------------------------------------


def safe_model_response_text(model, message, message_history):
    """Return model text or None when Gemini blocks/omits text."""
    try:
        return response_from_chatbot(model, message, message_history)
    except Exception as exc:
        print(f"Model response error: {exc}")
        return None


# --------------------------------------------------------------------------------------------------------------------------------


def get_chat_history_from_firestore(userDoc):
    """
    Retrieve chat history from Firestore for a specific user.

    Args:
        userDoc: Firestore document reference for the user

    Returns:
        List of Content objects representing the conversation history
    """
    chat_his: List[Content] = []
    if not userDoc.get().exists:
        return []

    conversation_query = userDoc.collection("conversation1").order_by("CountResponse")
    for doc in conversation_query.stream():
        content = doc.get("Content")
        response = doc.get("Response")
        if content is None or response is None:
            continue
        if str(content).startswith("__"):
            continue

        chat_his.append(Content(role="user", parts=[Part.from_text(content)]))
        chat_his.append(Content(role="model", parts=[Part.from_text(response)]))

    return chat_his


# --------------------------------------------------------------------------------------------------------------------------------


def load_chat_config(file_path):
    """
    Load chat configuration from a JSON file.

    Args:
        file_path: Path to the JSON configuration file

    Returns:
        Tuple of (context_string, samples_list)
    """
    with open(file_path, "r", encoding="utf-8") as file:
        config = json.load(file)
    return config["context"], config["samples"]


# --------------------------------------------------------------------------------------------------------------------------------


def init_chat_config(context, samples):
    """
    Initialize chat configuration with context and sample exchanges.

    Args:
        context: The system context/prompt string
        samples: List of sample input/output pairs

    Returns:
        List of Content objects for chat initialization
    """
    chat_history = [
        Content(role="user", parts=[Part.from_text(context)]),
        Content(role="model", parts=[Part.from_text("Understood.")]),
    ]

    for sample in samples:
        chat_history.append(Content(role="user", parts=[Part.from_text(sample["input"])]))
        chat_history.append(Content(role="model", parts=[Part.from_text(sample["output"])]))

    return chat_history


# --------------------------------------------------------------------------------------------------------------------------------


def augment_question_with_rag(question):
    """
    Augment user question with retrieval context when relevant.

    Args:
        question: The user's original question

    Returns:
        Tuple of (augmented_question, rag_used_flag, retrieved_sources, grounding_scope)
    """
    retrieval_question = normalize_intent_text(question)
    if not (should_retrieve(retrieval_question) or is_service_overview_question(retrieval_question) or needs_strict_grounding(retrieval_question)):
        return question, False, [], ""

    factual_core = build_finance_factual_core(question)
    rag_results = retrieve_context(retrieval_question, max_results=RAG_MAX_SOURCES)
    context_parts = []
    sources = []
    rag_scope = ""

    for index, result in enumerate(rag_results[:RAG_MAX_SOURCES], start=1):
        title = result.get("title", "Reference")
        snippet = (result.get("snippet", "") or "").strip()
        link = result.get("link", "")
        domain = result.get("domain", "")
        source_scope = result.get("source_scope", "")

        if not snippet:
            continue

        rag_scope = rag_scope or source_scope
        condensed_snippet = re.sub(r"\s+", " ", snippet)[:520]
        context_parts.append(f"[Source {index}] {title}: {condensed_snippet}")
        if link:
            sources.append(
                {
                    "title": title or "AmazingBank reference",
                    "link": link,
                    "domain": domain,
                    "source_scope": source_scope,
                }
            )

    reference_block = "\n".join(context_parts) if context_parts else "No external snippets retrieved for this turn."
    factual_block = factual_core if factual_core else "No catalog entry matched; stay practical and avoid unsupported specifics."

    augmented_question = f"""Use the evidence and factual core below.

Rules:
- Keep response under 120 words.
- Answer in English only.
- Use a neutral, direct, professional tone.
- Do not use emojis, emotion icons, empathy opener phrases, or emotional wording.
- Use only AmazingBank branding in your answer.
- Never mention source-bank names. Use "AmazingBank" or "other banks".
- Use generic service names: AmazingBank Mobile App, AmazingBank Online Banking, AmazingBank Investment Platform.
- Keep the same factual core used by all AmazingBank chatbot variants; tone differs but facts stay aligned.
- Mention concrete features or conditions only when supported by snippets or factual core.
- If an exact number, fee, rate, timeline, or policy detail is missing, say it is not fully verified.
- If reference snippets or source pages are in Vietnamese, interpret them and respond in natural English.

Shared factual core:
{factual_block}

Grounding scope:
{rag_scope or "none"}

Reference snippets:
{reference_block}

User question: {question}
"""
    return augmented_question, bool(context_parts), sources, rag_scope


# --------------------------------------------------------------------------------------------------------------------------------


def create_generative_model():
    """
    Create and configure the Vertex AI Generative Model.

    Returns:
        Configured GenerativeModel instance
    """
    return GenerativeModel(
        "gemini-2.5-flash",
        generation_config={
            "candidate_count": 1,
            # Allow richer, structured answers with concrete detail.
            "max_output_tokens": 384,
            # Balanced decoding for better natural responses with low hallucination risk.
            "temperature": 0.2,
            "top_p": 0.9,
        },
        safety_settings={
            generative_models.HarmCategory.HARM_CATEGORY_HATE_SPEECH: generative_models.HarmBlockThreshold.BLOCK_ONLY_HIGH,
            generative_models.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: generative_models.HarmBlockThreshold.BLOCK_ONLY_HIGH,
            generative_models.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: generative_models.HarmBlockThreshold.BLOCK_ONLY_HIGH,
            generative_models.HarmCategory.HARM_CATEGORY_HARASSMENT: generative_models.HarmBlockThreshold.BLOCK_ONLY_HIGH,
        },
    )


# --------------------------------------------------------------------------------------------------------------------------------


def save_message_to_firestore(
    userDoc,
    userID,
    question,
    response,
    history_length,
    rag_used=False,
    sources=None,
    response_mode="generated",
    cache_hit=False,
    turn_classification="substantive",
    grounding_scope="model_only",
):
    """
    Save a chat message to Firestore.

    Args:
        userDoc: Firestore document reference for the user
        userID: The user's unique identifier
        question: The user's question
        response: The model's response
        history_length: Current length of chat history after this turn
        rag_used: Whether RAG was used for this response
        sources: List of sources used (if RAG was used)
        response_mode: How the response was produced
        cache_hit: Whether deterministic cache served the response
        turn_classification: How the current user turn was classified
        grounding_scope: What grounding path informed the response
    """
    current_time = datetime.datetime.now()
    conversation = userDoc.collection("conversation1")

    if not userDoc.get().exists:
        userDoc.set(
            {
                "userHash": userID,
                "chatbotType": CHATBOT_TYPE,
                "createdAt": current_time,
            }
        )

    response_count = max(1, int(history_length / 2))
    new_message = conversation.document(f"message{response_count}")

    message_data = {
        "Content": question,
        "CreatedAt": current_time,
        "Response": response,
        "CountResponse": response_count,
        "RagUsed": rag_used,
        "ResponseMode": response_mode,
        "CacheHit": cache_hit,
        "CacheVersion": CACHE_VERSION,
        "TurnClassification": turn_classification,
        "GroundingScope": grounding_scope,
    }

    if sources:
        message_data["Sources"] = sources

    new_message.set(message_data)
    return response_count


# --------------------------------------------------------------------------------------------------------------------------------


def end_chat_session(userDoc):
    """Delete a user's stored chat session."""
    if not userDoc.get().exists:
        return

    for doc in userDoc.collection("conversation1").stream():
        doc.reference.delete()
    userDoc.delete()


# --------------------------------------------------------------------------------------------------------------------------------


def build_response_payload(response, response_count, rag_used, response_mode, cache_hit, turn_classification, grounding_scope):
    """Create API payload for chatbot responses."""
    return {
        "response": response,
        "data": response_count,
        "rag_used": rag_used,
        "response_mode": response_mode,
        "cache_hit": cache_hit,
        "cache_version": CACHE_VERSION,
        "turn_classification": turn_classification,
        "grounding_scope": grounding_scope,
    }


# --------------------------------------------------------------------------------------------------------------------------------


def maybe_bootstrap_session(userDoc, userID, init_conversation: bool, question: str, headers):
    has_history = userDoc.collection("conversation1").document("message1").get().exists
    if has_history:
        return None

    if init_conversation and not question:
        response_count = save_message_to_firestore(
            userDoc,
            userID,
            "__INIT__",
            FIXED_OPENING_MESSAGE,
            history_length=2,
            rag_used=False,
            sources=None,
            response_mode="init",
            cache_hit=False,
            turn_classification="empty",
            grounding_scope="init",
        )
        data = build_response_payload(FIXED_OPENING_MESSAGE, response_count, False, "init", False, "empty", "init")
        data["userHash"] = userID
        return jsonify(data), 200, headers

    return None


# --------------------------------------------------------------------------------------------------------------------------------


@functions_framework.http
def entry(request):
    """
    Main entry point for the Cloud Function HTTP trigger.

    Handles CORS preflight requests and processes chat messages.
    """
    if request.method == "OPTIONS":
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Max-Age": "3600",
        }
        return "", 204, headers

    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    }

    try:
        request_json = request.get_json(silent=True) or {}
        userID = request_json.get("userHash", "")
        question = (request_json.get("question", "") or "").strip()
        init_conversation = bool(request_json.get("initConversation", False))
        end_chat = bool(request_json.get("endChat", False))
        bypass_cache = bool(request_json.get("bypassCache", False))

        if not userID:
            userID = str(uuid.uuid4())

        db = init_firestore_client()
        userDoc = db.collection("Users").document(userID)

        if end_chat:
            end_chat_session(userDoc)
            return jsonify({"status": "ended", "userHash": userID}), 200, headers

        bootstrapped = maybe_bootstrap_session(userDoc, userID, init_conversation, question, headers)
        if bootstrapped is not None:
            return bootstrapped

        chat_history = get_chat_history_from_firestore(userDoc)
        chat_history_length = len(chat_history)
        turn_classification = get_turn_classification(question)

        if turn_classification == "empty":
            response = finalize_response(
                "I am ready when you want to continue with an AmazingBank question.",
                question,
                rag_used=False,
                response_mode="policy",
                force_fallback=False,
                turn_classification=turn_classification,
            )
            grounding_scope = determine_grounding_scope("policy", False, "", turn_classification)
            response_count = save_message_to_firestore(
                userDoc,
                userID,
                "__EMPTY__",
                response,
                history_length=chat_history_length + 2,
                rag_used=False,
                sources=None,
                response_mode="policy",
                cache_hit=False,
                turn_classification=turn_classification,
                grounding_scope=grounding_scope,
            )
            data = build_response_payload(response, response_count, False, "policy", False, turn_classification, grounding_scope)
            data["userHash"] = userID
            return jsonify(data), 200, headers

        if turn_classification != "substantive":
            response = finalize_response(
                "",
                question,
                rag_used=False,
                response_mode="policy",
                force_fallback=False,
                turn_classification=turn_classification,
            )
            grounding_scope = determine_grounding_scope("policy", False, "", turn_classification)
            response_count = save_message_to_firestore(
                userDoc,
                userID,
                question,
                response,
                history_length=chat_history_length + 2,
                rag_used=False,
                sources=None,
                response_mode="policy",
                cache_hit=False,
                turn_classification=turn_classification,
                grounding_scope=grounding_scope,
            )
            data = build_response_payload(response, response_count, False, "policy", False, turn_classification, grounding_scope)
            data["userHash"] = userID
            return jsonify(data), 200, headers

        normalized_question = normalize_question(question)
        cached_response = None if bypass_cache else get_cached_response(db, normalized_question)

        rag_used = False
        cache_hit = False
        response_mode = "generated"
        sources = []
        grounding_scope = "model_only"

        if cached_response and cached_response.get("response"):
            cached_rag_used = bool(cached_response.get("ragUsed", False))
            cached_mode = cached_response.get("responseMode", "generated")
            cached_grounding_scope = cached_response.get("groundingScope") or determine_grounding_scope(
                cached_mode,
                cached_rag_used,
                "",
                turn_classification,
            )
            repaired_response = finalize_response(
                cached_response["response"],
                question,
                cached_rag_used,
                response_mode=cached_mode,
                turn_classification=turn_classification,
            )
            if not is_bad_cached_response(repaired_response, question, cached_mode, cached_grounding_scope, cached_rag_used):
                response = repaired_response
                rag_used = cached_rag_used
                response_mode = cached_mode
                grounding_scope = cached_grounding_scope
                cache_hit = True

        if not cache_hit:
            playbook: Optional[PlaybookResult] = build_playbook_response(question)
            if playbook is not None:
                response_mode = playbook.response_mode
                grounding_scope = determine_grounding_scope(response_mode, False, "", turn_classification)
                response = finalize_response(
                    playbook.text,
                    question,
                    rag_used=False,
                    response_mode=response_mode,
                    force_fallback=False,
                    turn_classification=turn_classification,
                )
                if not bypass_cache and should_cache_response(
                    response,
                    question,
                    response_mode,
                    grounding_scope,
                    False,
                ):
                    save_cached_response(db, normalized_question, response, False, response_mode, grounding_scope)
            else:
                model = create_generative_model()
                if int(chat_history_length / 2) <= 1:
                    context, samples = load_chat_config("follow_up_config.json")
                else:
                    context, samples = load_chat_config("chat_config.json")

                prompt = init_chat_config(context, samples)
                augmented_question, rag_used, sources, rag_scope = augment_question_with_rag(question)
                force_fallback = needs_strict_grounding(question) and not rag_used

                if force_fallback:
                    model_response = build_live_verification_fallback(question)
                    response_mode = "live-fallback"
                else:
                    concat_his = prompt + chat_history
                    model_response = safe_model_response_text(model, augmented_question, concat_his)
                    if model_response:
                        response_mode = "generated"
                    else:
                        model_response = GENERAL_SUPPORT_FALLBACK
                        response_mode = "policy"

                grounding_scope = determine_grounding_scope(response_mode, rag_used, rag_scope, turn_classification)
                response = finalize_response(
                    model_response,
                    question,
                    rag_used,
                    response_mode=response_mode,
                    force_fallback=force_fallback,
                    turn_classification=turn_classification,
                )
                if not bypass_cache and should_cache_response(
                    response,
                    question,
                    response_mode,
                    grounding_scope,
                    rag_used,
                ):
                    save_cached_response(db, normalized_question, response, rag_used, response_mode, grounding_scope)

        response_count = save_message_to_firestore(
            userDoc,
            userID,
            question,
            response,
            history_length=chat_history_length + 2,
            rag_used=rag_used,
            sources=sources,
            response_mode=response_mode,
            cache_hit=cache_hit,
            turn_classification=turn_classification,
            grounding_scope=grounding_scope,
        )

        data = build_response_payload(
            response,
            response_count,
            rag_used,
            response_mode,
            cache_hit,
            turn_classification,
            grounding_scope,
        )
        data["userHash"] = userID
        return jsonify(data), 200, headers

    except Exception as e:
        response = jsonify({"error": str(e)})
        return response, HTTPStatus.INTERNAL_SERVER_ERROR, headers


# --------------------------------------------------------------------------------------------------------------------------------


@functions_framework.http
def health_check(request):
    """
    Health check endpoint for monitoring.
    """
    headers = {
        "Access-Control-Allow-Origin": "*",
    }
    return jsonify({"status": "healthy", "service": CHATBOT_TYPE}), 200, headers
