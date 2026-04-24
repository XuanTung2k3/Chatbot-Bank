import datetime
import hashlib
import json
import os
import re
import uuid
from http import HTTPStatus
from typing import List, Optional

import functions_framework
import vertexai
import vertexai.preview.generative_models as generative_models
from banking_playbooks import PlaybookResult, build_playbook_response
from flask import jsonify
from google.cloud import firestore
from rag_retriever import retrieve_context, should_retrieve
from turn_classifier import classify_turn as classify_social_turn, normalize_turn
from vertexai.generative_models import Content, GenerativeModel, Part

# --------------------------------------------------------------------------------------------------------------------------------

PROJECT_ID = "gen-lang-client-0975766004"
CHATBOT_TYPE = "amazingbank-empathetic-rag"
GLOBAL_CACHE_COLLECTION = "GlobalQuestionAnswerCacheFinanceEmpathetic"
CACHE_VERSION = "v11"
MAX_RESPONSE_WORDS = 120
MIN_DETAILED_RESPONSE_WORDS = 70
RAG_MAX_SOURCES = 5
PUBLIC_BANK_NAME = os.getenv("PUBLIC_BANK_NAME", "AmazingBank").strip() or "AmazingBank"
SOURCE_BANK_NAME = os.getenv("SOURCE_BANK_NAME", "").strip()
SOURCE_BANK_SHORT_NAME = os.getenv("SOURCE_BANK_SHORT_NAME", "").strip()

FIXED_OPENING_MESSAGE = (
    "Hello and welcome! 👋 I'm your friendly financial advisor at AmazingBank. "
    "I can help with cards, loans, savings, transfers, security, and practical next steps. "
    "What would you like to solve today?"
)

LIVE_VERIFICATION_FALLBACK = (
    "I do not want to guess an exact live AmazingBank figure here. Please check the official AmazingBank channel for the latest number, "
    "and I can still help you compare the right options and questions to ask."
)

GENERAL_SUPPORT_FALLBACK = (
    "I want to keep this useful and accurate. I can still help with practical next steps if you share your exact goal, budget, and timeline. "
    "For exact AmazingBank-only details, please use the official AmazingBank support channel."
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
    r"\bcurrent\b",
    r"\btoday\b",
    r"\blatest\b",
    r"\blive\b",
    r"\bexact\b",
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
    r"\bprocessing time\b",
    r"\bwithin\s+\d+",
    r"\d+\s*%",
]

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

FINANCE_FACTUAL_CATALOG = {
    "cards": (
        "AmazingBank card services generally include debit and credit categories. "
        "Compare options by spending pattern, benefit type, installment eligibility, annual-fee tier, and digital controls in AmazingBank Mobile App."
    ),
    "loans": (
        "AmazingBank borrowing options can be compared by purpose, monthly affordability, repayment term, document requirements, and whether collateral is needed. "
        "AmazingBank Mobile App and branch support can both help start the process."
    ),
    "savings": (
        "AmazingBank savings planning usually comes down to flexibility versus return. Compare access needs, term length, balance stability, and digital management in AmazingBank Online Banking."
    ),
    "digital": (
        "AmazingBank digital services include AmazingBank Mobile App and AmazingBank Online Banking. Common needs include transfers, bill payment, alerts, card controls, and security settings."
    ),
    "investment": (
        "AmazingBank Investment Platform can support fund and bond access alongside savings planning. The right choice depends on time horizon, liquidity need, and risk tolerance."
    ),
}

INTENT_KEYWORDS = {
    "cards": ["card", "cards", "credit", "debit", "visa", "mastercard", "thẻ", "the", "tin dung"],
    "loans": ["loan", "loans", "mortgage", "home loan", "vay", "installment", "tra gop", "trả góp", "repayment"],
    "savings": ["saving", "savings", "deposit", "term", "tiết kiệm", "tiet kiem", "gui", "gửi"],
    "digital": ["app", "online banking", "mobile banking", "ebanking", "security", "otp", "transfer", "payment"],
    "investment": ["invest", "investment", "fund", "bond", "portfolio"],
}

FINANCE_DISTRESS_KEYWORDS = [
    "panic", "panicking", "stressed", "stress", "worried", "frustrated", "urgent", "scared",
    "lo lắng", "hoảng", "gấp", "căng thẳng",
]

EMPATHY_MARKERS = [
    "i understand",
    "i hear you",
    "thanks for raising this",
    "this can feel",
    "that sounds",
    "let us keep",
    "let us make",
    "we can keep",
    "i can help",
    "support",
    "guide",
]

DISTRESS_EMPATHY_OPENERS = [
    "That sounds stressful, and we can handle it step by step.",
    "I understand the urgency here, and we can keep it practical.",
    "I am sorry this happened, and I will keep the next steps clear.",
]

GENERAL_EMPATHY_OPENERS = [
    "Thanks for raising this.",
    "I can help you work through this clearly.",
    "Let us keep this straightforward.",
]

EMPATHY_ICONS = ["🤝", "💙", "🌟", "😊", "🔐", "📌"]

EMOJI_PATTERN = re.compile(
    "[" "\U0001F300-\U0001FAFF" "\U00002600-\U000027BF" "\U0001F1E6-\U0001F1FF" "]+",
    flags=re.UNICODE,
)

ACKNOWLEDGEMENT_RESPONSE = (
    "You are very welcome. I am here whenever you want to explore AmazingBank options again. 😊"
)
UNCLEAR_INPUT_RESPONSE = (
    "I want to guide you clearly. Could you share the AmazingBank service or issue you want help with? 💬"
)
GREETING_RESPONSE = "Hello again. I am here to help with AmazingBank services whenever you are ready. 😊"

ACKNOWLEDGEMENT_PATTERNS = [
    r"^(ok|okay|thanks|thank you|thx|ty|got it|understood|that'?s all|that is all|bye|goodbye)\b",
    r"^(cảm ơn|cam on|xong rồi|tạm biệt)\b",
]

GREETING_PATTERNS = [
    r"^(hi|hello|hey|good morning|good afternoon|good evening)\b",
    r"^(xin chào|chào)\b",
]

BROAD_PRODUCT_HINTS = [
    "what credit cards do you offer",
    "tell me about card service",
    "talk about loan",
    "loan service",
    "investment options",
    "what investment options",
    "tell me about savings",
    "what products do you offer",
]

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

# --------------------------------------------------------------------------------------------------------------------------------


def init_firestore_client() -> firestore.Client:
    return firestore.Client(project=PROJECT_ID)


# --------------------------------------------------------------------------------------------------------------------------------


def normalize_question(question: str) -> str:
    return normalize_turn(question)


# --------------------------------------------------------------------------------------------------------------------------------


def normalize_intent_text(question: str) -> str:
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
    return hashlib.sha256(normalized_question.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------------------------------------------------------------


def trim_to_word_limit(text: str, max_words: int = MAX_RESPONSE_WORDS) -> str:
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
    sanitized = (text or "").strip()
    if not sanitized:
        return ""

    for pattern, replacement in SERVICE_REPLACEMENTS.items():
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

    sanitized = _replace_source_bank_branding(sanitized)

    for pattern in OTHER_BANK_PATTERNS:
        sanitized = re.sub(pattern, "other banks", sanitized, flags=re.IGNORECASE)

    sanitized = re.sub(
        r"\b(?:\+?84[\s\-.]?)?(?:1800|1900)[\s\-.]?\d{3}[\s\-.]?\d{3}\b",
        "official AmazingBank support channel",
        sanitized,
        flags=re.IGNORECASE,
    )
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    return sanitized


# --------------------------------------------------------------------------------------------------------------------------------


def needs_strict_grounding(question: str) -> bool:
    question_lower = normalize_intent_text(question)
    return any(re.search(pattern, question_lower, flags=re.IGNORECASE) for pattern in STRICT_FACT_PATTERNS)


# --------------------------------------------------------------------------------------------------------------------------------


def is_acknowledgement_or_closer(question: str) -> bool:
    return get_turn_classification(question) == "ack_only"


# --------------------------------------------------------------------------------------------------------------------------------


def is_greeting(question: str) -> bool:
    return get_turn_classification(question) == "greeting_only"


# --------------------------------------------------------------------------------------------------------------------------------


def detect_finance_intent(question: str) -> str:
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
            "I do not want to guess the exact AmazingBank annual fee here because the amount can vary by card type and tier. "
            "Please check the official AmazingBank fee schedule or the specific card page for the latest posted annual fee, and I can still help you compare the right fee questions and card tradeoffs."
        )

    if focus == "savings_rate":
        return (
            "I do not want to guess the current AmazingBank savings rate here because the exact rate can depend on product type, balance tier, term, and channel. "
            "Please check the official AmazingBank savings page or support channel for the latest posted rate, and I can still help you compare flexible-access and fixed-term savings questions."
        )

    if focus == "mortgage_rate":
        return (
            "I do not want to guess the current AmazingBank mortgage rate here because the final rate can vary by product, borrower profile, and loan structure. "
            "Please check the official AmazingBank mortgage or home-loan page for the latest posted rate, and I can still help you compare affordability points and the key rate questions to ask."
        )

    if focus == "transfer_fee":
        return (
            "I do not want to guess the exact AmazingBank transfer fee here because pricing can depend on domestic versus international routing, channel, currency, urgency, and your account package. "
            "Please check the official AmazingBank fee schedule or support channel for the latest posted transfer fee."
        )

    if focus == "transfer_limit":
        return (
            "I do not want to guess the exact AmazingBank transfer limit here because limits can depend on channel, verification status, destination, and security settings. "
            "Please check the official AmazingBank limits information or support channel for the current posted transfer limit on your profile."
        )

    if focus == "monthly_account_fee":
        return (
            "I do not want to guess the exact AmazingBank monthly account fee here because the amount can vary by account type, package, and waiver conditions. "
            "Please check the official AmazingBank fee schedule or support channel for the latest posted monthly account fee."
        )

    if focus == "atm_fee":
        return (
            "I do not want to guess the exact AmazingBank ATM withdrawal fee here because fee treatment can depend on your card type, the ATM network, and whether the withdrawal is domestic or international. "
            "Please check the official AmazingBank fee schedule or support channel for the latest posted ATM policy."
        )

    if focus == "service_hours":
        if "weekend" in normalize_intent_text(question):
            return (
                "AmazingBank Mobile App and AmazingBank Online Banking may still be available for self-service at any time, but I do not want to guess staffed weekend support here. "
                "Please check the official AmazingBank contact page or support channel for the latest weekend hours for phone, chat, or branch assistance."
            )
        return (
            "I do not want to guess the exact AmazingBank customer service hours here because they can vary by channel, branch, and day. "
            "Please check the official AmazingBank contact page, Mobile App, Online Banking, or branch listing for the latest hours, and I can still help you choose the quickest support path."
        )

    return LIVE_VERIFICATION_FALLBACK


# --------------------------------------------------------------------------------------------------------------------------------


def is_broad_product_question(question: str) -> bool:
    normalized = normalize_intent_text(question)
    if any(hint in normalized for hint in BROAD_PRODUCT_HINTS):
        return True
    if needs_strict_grounding(question):
        return False
    if build_playbook_response(question):
        return False
    intent = detect_finance_intent(question)
    if intent and any(word in normalized for word in ["offer", "options", "service", "benefit", "compare", "best fit", "best for me"]):
        return True
    return False


# --------------------------------------------------------------------------------------------------------------------------------


def allow_next_step_prompt(question: str, response_mode: str) -> bool:
    if response_mode in {"live-fallback", "policy", "playbook"}:
        return False
    return is_broad_product_question(question)


# --------------------------------------------------------------------------------------------------------------------------------


def is_unclear_or_prompt_attack(question: str) -> bool:
    normalized = normalize_question(question)
    if any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in PROMPT_INJECTION_PATTERNS):
        return True
    return any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in UNCLEAR_INPUT_PATTERNS)


# --------------------------------------------------------------------------------------------------------------------------------


def _is_short_non_actionable_input(question: str) -> bool:
    normalized = normalize_question(question)
    if not normalized:
        return False
    if (
        needs_strict_grounding(normalized)
        or is_unclear_or_prompt_attack(normalized)
        or detect_finance_intent(normalized)
        or build_playbook_response(normalized)
        or is_broad_product_question(normalized)
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
    return get_turn_classification(question) == "unclear"


# --------------------------------------------------------------------------------------------------------------------------------


def dedupe_repeated_sentences(text: str) -> str:
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


def contains_blocked_output(text: str) -> bool:
    content = (text or "").lower()
    return any(re.search(pattern, content, flags=re.IGNORECASE) for pattern in BLOCKED_OUTPUT_PATTERNS)


# --------------------------------------------------------------------------------------------------------------------------------


def sanitize_blocked_output(text: str) -> str:
    if contains_blocked_output(text):
        return GENERAL_SUPPORT_FALLBACK
    return text


# --------------------------------------------------------------------------------------------------------------------------------


def build_finance_factual_core(question: str) -> str:
    if not is_broad_product_question(question):
        return ""
    intent = detect_finance_intent(question)
    return FINANCE_FACTUAL_CATALOG.get(intent, "")


# --------------------------------------------------------------------------------------------------------------------------------


def ensure_factual_core_alignment(text: str, question: str) -> str:
    content = (text or "").strip()
    factual_core = build_finance_factual_core(question)
    if not content or not factual_core:
        return content
    if len(content.split()) >= MIN_DETAILED_RESPONSE_WORDS:
        return content
    if factual_core.lower() in content.lower():
        return content
    return f"{factual_core} {content}".strip()


# --------------------------------------------------------------------------------------------------------------------------------


def ensure_soft_empathy(text: str, question: str) -> str:
    content = (text or "").strip()
    if not content:
        return ""
    lowered = content.lower()
    if any(marker in lowered for marker in EMPATHY_MARKERS):
        return content

    seed_source = normalize_question(question) or content.lower()
    seed = int(hashlib.sha256(seed_source.encode("utf-8")).hexdigest(), 16)
    distress = any(keyword in normalize_question(question) for keyword in FINANCE_DISTRESS_KEYWORDS)
    opener_pool = DISTRESS_EMPATHY_OPENERS if distress else GENERAL_EMPATHY_OPENERS
    opener = opener_pool[seed % len(opener_pool)]
    return f"{opener} {content}".strip()


# --------------------------------------------------------------------------------------------------------------------------------


def ensure_empathy_icon(text: str, question: str) -> str:
    content = (text or "").strip()
    if not content:
        return ""
    if EMOJI_PATTERN.search(content):
        return content
    seed_source = normalize_question(question) or content.lower()
    seed = int(hashlib.sha256(seed_source.encode("utf-8")).hexdigest(), 16)
    icon = EMPATHY_ICONS[seed % len(EMPATHY_ICONS)]
    return f"{content} {icon}".strip()


# --------------------------------------------------------------------------------------------------------------------------------


def add_next_step_prompt(text: str, question: str, response_mode: str) -> str:
    content = (text or "").strip()
    if not content or not allow_next_step_prompt(question, response_mode):
        return content

    lowered = content.lower()
    if any(marker in lowered for marker in ["tell me your", "share your", "if you share", "if you tell me"]):
        return content

    intent = detect_finance_intent(question)
    prompts = {
        "cards": "If you share your common monthly spending categories, I can narrow the best-fit card instead of listing every option.",
        "loans": "If you share the purpose, amount, and monthly budget, I can help narrow the most practical borrowing path.",
        "savings": "If you share your timeline and whether flexibility matters, I can help compare the right savings setup.",
        "investment": "If you share your target timeline and risk comfort, I can help frame a sensible starting approach.",
        "digital": "If you share the exact task you are trying to complete, I can point you to the quickest secure path.",
    }
    prompt = prompts.get(intent)
    if not prompt:
        return content
    return f"{content} {prompt}".strip()


# --------------------------------------------------------------------------------------------------------------------------------


def response_meets_style_requirements(text: str, question: str) -> bool:
    content = (text or "").strip()
    if not content:
        return False
    if is_acknowledgement_or_closer(question) or is_greeting(question):
        return True
    lowered = content.lower()
    return bool(EMOJI_PATTERN.search(content)) and any(marker in lowered for marker in EMPATHY_MARKERS)


# --------------------------------------------------------------------------------------------------------------------------------


def has_duplicate_sentence(text: str) -> bool:
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


def is_bad_cached_response(
    text: str,
    question: str,
    response_mode: str = "generated",
    grounding_scope: str = "model_only",
    rag_used: bool = False,
) -> bool:
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
    response_mode: str,
    force_fallback: bool = False,
    turn_classification: Optional[str] = None,
) -> str:
    response = sanitize_blocked_output((raw_response or "").strip())
    turn_classification = turn_classification or get_turn_classification(question)

    if turn_classification == "ack_only":
        return trim_to_word_limit(ACKNOWLEDGEMENT_RESPONSE)

    if turn_classification == "greeting_only":
        return trim_to_word_limit(GREETING_RESPONSE)

    if turn_classification == "unclear":
        return trim_to_word_limit(UNCLEAR_INPUT_RESPONSE)

    if force_fallback and not response:
        response = build_live_verification_fallback(question)
    elif not response:
        response = GENERAL_SUPPORT_FALLBACK

    if needs_strict_grounding(question) and not rag_used and response_mode == "generated":
        response = build_live_verification_fallback(question)
        response_mode = "live-fallback"

    response = sanitize_bank_and_service_terms(response)
    response = ensure_factual_core_alignment(response, question)
    response = ensure_soft_empathy(response, question)
    response = dedupe_repeated_sentences(response)
    response = add_next_step_prompt(response, question, response_mode)
    response = sanitize_bank_and_service_terms(response)
    response = ensure_empathy_icon(response, question)
    response = dedupe_repeated_sentences(response)
    response = trim_to_word_limit(response)

    if not any(marker in response.lower() for marker in EMPATHY_MARKERS):
        response = trim_to_word_limit(ensure_empathy_icon(ensure_soft_empathy(response, question), question))
    if not EMOJI_PATTERN.search(response):
        response = trim_to_word_limit(ensure_empathy_icon(response, question))

    return trim_to_word_limit(dedupe_repeated_sentences(sanitize_blocked_output(response)))


# --------------------------------------------------------------------------------------------------------------------------------


def get_cached_response(db: firestore.Client, normalized_question: str):
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
    chat = model.start_chat(history=message_history)
    model_response = chat.send_message(message)
    text = getattr(model_response, "text", None)
    if not text:
        raise ValueError("Empty model response text")
    return text


# --------------------------------------------------------------------------------------------------------------------------------


def safe_model_response_text(model, message, message_history) -> Optional[str]:
    try:
        return response_from_chatbot(model, message, message_history)
    except Exception as exc:
        print(f"Model response error: {exc}")
        return None


# --------------------------------------------------------------------------------------------------------------------------------


def get_chat_history_from_firestore(userDoc) -> List[Content]:
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
    with open(file_path, "r", encoding="utf-8") as file:
        config = json.load(file)
    return config["context"], config["samples"]


# --------------------------------------------------------------------------------------------------------------------------------


def init_chat_config(context, samples):
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
    retrieval_question = normalize_intent_text(question)
    if not (should_retrieve(retrieval_question) or is_broad_product_question(retrieval_question) or needs_strict_grounding(retrieval_question)):
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

    reference_block = "\n".join(context_parts) if context_parts else "No verified snippets retrieved for this turn."
    factual_block = factual_core if factual_core else "No catalog note matched. Give practical guidance, do not invent exact live details, and never upsell unrelated products."

    augmented_question = f"""Use the evidence and rules below.

Rules:
- Keep the response under 120 words.
- Answer in English only.
- Answer the user question directly before any optional follow-up.
- Never push unrelated products.
- For loss, fraud, wrong-transfer, security, or urgent service problems: give immediate steps first, then official support guidance.
- When exact live numbers or bank-only policies are missing, say they are not verified in this chat and do not invent them.
- You may still give general educational guidance when it helps the user make a safer or clearer decision.
- Use only AmazingBank branding and generic service names.
- Include one suitable emotional icon.
- If reference snippets or source pages are in Vietnamese, interpret them and respond in natural English.

Shared factual core:
{factual_block}

Grounding scope:
{rag_scope or "none"}

Verified snippets:
{reference_block}

User question: {question}
"""
    return augmented_question, bool(context_parts), sources, rag_scope


# --------------------------------------------------------------------------------------------------------------------------------


def create_generative_model():
    vertexai.init(project=PROJECT_ID)
    return GenerativeModel(
        "gemini-2.5-flash",
        generation_config={
            "candidate_count": 1,
            "max_output_tokens": 384,
            "temperature": 0.15,
            "top_p": 0.85,
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
    if not userDoc.get().exists:
        return
    for doc in userDoc.collection("conversation1").stream():
        doc.reference.delete()
    userDoc.delete()


# --------------------------------------------------------------------------------------------------------------------------------


def build_response_payload(response, response_count, rag_used, response_mode, cache_hit, turn_classification, grounding_scope):
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

    # Do not consume the user's first real question anymore.
    return None


# --------------------------------------------------------------------------------------------------------------------------------


@functions_framework.http
def entry(request):
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
        userID = request_json.get("userHash", "") or str(uuid.uuid4())
        question = (request_json.get("question", "") or "").strip()
        init_conversation = bool(request_json.get("initConversation", False))
        end_chat = bool(request_json.get("endChat", False))
        bypass_cache = bool(request_json.get("bypassCache", False))

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
                "I am ready whenever you want to continue with an AmazingBank question.",
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
                force_fallback=False,
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
                config_path = "follow_up_config.json" if int(chat_history_length / 2) <= 1 else "chat_config.json"
                context, samples = load_chat_config(config_path)
                prompt = init_chat_config(context, samples)
                augmented_question, rag_used, sources, rag_scope = augment_question_with_rag(question)
                force_fallback = needs_strict_grounding(question) and not rag_used

                if force_fallback:
                    raw_response = build_live_verification_fallback(question)
                    response_mode = "live-fallback"
                else:
                    concat_his = prompt + chat_history
                    raw_response = safe_model_response_text(model, augmented_question, concat_his)
                    if raw_response:
                        response_mode = "generated"
                    else:
                        raw_response = GENERAL_SUPPORT_FALLBACK
                        response_mode = "policy"

                grounding_scope = determine_grounding_scope(response_mode, rag_used, rag_scope, turn_classification)
                response = finalize_response(
                    raw_response,
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
    headers = {
        "Access-Control-Allow-Origin": "*",
    }
    return jsonify({"status": "healthy", "service": CHATBOT_TYPE}), 200, headers
