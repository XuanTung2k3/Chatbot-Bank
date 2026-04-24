import os
import re
import time
import unicodedata
from typing import Dict, List, Set
from urllib.parse import urlparse

import requests

# Keep credentials out of source code. Configure these in deployment.
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
SEARCH_ENGINE_ID = os.getenv("SEARCH_ENGINE_ID", "")

# Public-facing chatbot brand and hidden retrieval source bank.
PUBLIC_BANK_NAME = os.getenv("PUBLIC_BANK_NAME", "AmazingBank").strip() or "AmazingBank"
SOURCE_BANK_NAME = os.getenv("SOURCE_BANK_NAME", "").strip()
SOURCE_BANK_SHORT_NAME = os.getenv("SOURCE_BANK_SHORT_NAME", "").strip()

# Comma-separated allowlist of official source domains used for retrieval.
OFFICIAL_BANK_DOMAINS = tuple(
    domain.strip().lower()
    for domain in os.getenv("OFFICIAL_BANK_DOMAINS", "").split(",")
    if domain.strip()
)

# Fallback public guidance domains when official bank domains are not configured.
PUBLIC_GUIDANCE_DOMAINS = (
    "consumerfinance.gov",
    "fdic.gov",
    "ask.fdic.gov",
)

PUBLIC_GUIDANCE_KEYWORDS = [
    "fraud", "unauthorized", "unauthorised", "security", "secure", "safe",
    "phishing", "otp", "scam", "identity theft", "wrong transfer", "lost card",
    "stolen card", "dispute", "report", "consumer protection", "liability",
    "protect my account", "secure online banking",
]

VIETNAMESE_QUERY_HINTS = {
    "account_documents": [
        "mở tài khoản giấy tờ",
        "hồ sơ mở tài khoản",
        "giấy tờ mở tài khoản thanh toán",
    ],
    "account_opening": [
        "mở tài khoản thanh toán",
        "mở tài khoản ngân hàng",
        "điều kiện mở tài khoản",
    ],
    "card_fee": [
        "phí thường niên thẻ tín dụng",
        "biểu phí thẻ tín dụng",
        "thẻ tín dụng phí",
    ],
    "cards": [
        "thẻ tín dụng",
        "thẻ thanh toán",
        "mở thẻ",
    ],
    "savings": [
        "tiết kiệm",
        "gửi tiết kiệm",
        "lãi suất tiết kiệm",
    ],
    "loans": [
        "vay",
        "hồ sơ vay",
        "điều kiện vay",
    ],
    "mortgage_rates": [
        "lãi suất vay mua nhà",
        "lãi suất vay thế chấp",
        "vay mua nhà lãi suất",
    ],
    "transfer": [
        "chuyển khoản",
        "chuyển tiền nhầm",
        "tra soát chuyển khoản",
    ],
    "international_transfer": [
        "chuyển tiền quốc tế",
        "chuyển tiền ra nước ngoài",
        "swift bic chuyển tiền",
        "phí chuyển tiền quốc tế",
    ],
    "security": [
        "bảo mật",
        "giao dịch bất thường",
        "lừa đảo otp",
    ],
    "digital": [
        "ngân hàng điện tử",
        "ứng dụng ngân hàng",
        "internet banking",
    ],
    "service_hours": [
        "giờ làm việc",
        "giờ hỗ trợ khách hàng",
        "tổng đài giờ làm việc",
        "chi nhánh giờ làm việc",
    ],
}

BANKING_KEYWORDS = [
    "amazingbank", "bank", "credit card", "visa", "mastercard", "loan", "mortgage",
    "savings", "interest rate", "annual fee", "cashback", "rewards", "thẻ tín dụng",
    "vay", "tiết kiệm", "tài khoản", "account", "transfer", "chuyển khoản",
    "lãi suất", "phí", "atm", "mobile banking", "online banking", "installment",
    "trả góp", "credit limit", "hạn mức", "debit card", "deposit", "withdraw",
    "otp", "security", "secure", "hotline", "fraud", "unauthorized", "wrong transfer",
]

SERVICE_INTENT_KEYWORDS = [
    "card", "cards", "loan", "loans", "savings", "saving", "deposit", "account",
    "app", "online banking", "mobile banking", "investment", "transfer", "payment",
    "dịch vụ", "thẻ", "vay", "tiết kiệm", "tài khoản", "ứng dụng",
]

STOPWORDS = {
    "the", "a", "an", "and", "or", "for", "to", "of", "in", "on", "with",
    "about", "how", "what", "is", "are", "do", "does", "can", "i", "me", "my",
    "you", "your", "please", "bank", "amazingbank",
}

SEARCH_TIMEOUT_SECONDS = 5.0
CACHE_TTL_SECONDS = 300
MAX_CACHE_ENTRIES = 128

_SEARCH_CACHE: Dict[str, tuple] = {}
_RETRIEVE_CACHE: Dict[str, tuple] = {}


def _cache_get(cache: Dict[str, tuple], key: str):
    entry = cache.get(key)
    if not entry:
        return None
    timestamp, value = entry
    if (time.time() - timestamp) > CACHE_TTL_SECONDS:
        cache.pop(key, None)
        return None
    return value


def _cache_set(cache: Dict[str, tuple], key: str, value):
    if len(cache) >= MAX_CACHE_ENTRIES:
        oldest_key = min(cache.items(), key=lambda item: item[1][0])[0]
        cache.pop(oldest_key, None)
    cache[key] = (time.time(), value)


def _fold_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _tokenize(text: str) -> Set[str]:
    tokens = re.findall(r"[a-z0-9]+", _fold_text(text))
    return {token for token in tokens if len(token) > 1 and token not in STOPWORDS}


def should_retrieve(question: str) -> bool:
    question_lower = (question or "").lower()
    return any(keyword in question_lower for keyword in BANKING_KEYWORDS + SERVICE_INTENT_KEYWORDS)


def _official_source_enabled() -> bool:
    return bool(OFFICIAL_BANK_DOMAINS)


def _source_bank_tokens() -> List[str]:
    tokens = [SOURCE_BANK_NAME.strip(), SOURCE_BANK_SHORT_NAME.strip()]
    return [token for token in tokens if token]


def retrieval_scope_for_question(question: str) -> str:
    if _official_source_enabled():
        return "official_rag"

    question_lower = (question or "").lower()
    if any(keyword in question_lower for keyword in PUBLIC_GUIDANCE_KEYWORDS):
        return "public_guidance"

    return ""


def _allowed_domains(question: str) -> tuple:
    scope = retrieval_scope_for_question(question)
    if scope == "official_rag":
        return OFFICIAL_BANK_DOMAINS
    if scope == "public_guidance":
        return PUBLIC_GUIDANCE_DOMAINS
    return ()


def _is_trusted_source(link: str, allowed_domains: tuple) -> bool:
    if not link or not allowed_domains:
        return False
    netloc = urlparse(link).netloc.lower()
    return any(netloc.endswith(domain) for domain in allowed_domains)


def _build_site_clause(domains: tuple) -> str:
    if not domains:
        return ""
    return " OR ".join(f"site:{domain}" for domain in domains)


def _has_any_term(text: str, terms: List[str]) -> bool:
    folded_text = _fold_text(text)
    return any(_fold_text(term) in folded_text for term in terms)


def _english_to_vietnamese_hints(question: str) -> List[str]:
    hints: List[str] = []
    question_folded = _fold_text(question)

    if _has_any_term(question_folded, ["account", "checking account", "payment account"]):
        if _has_any_term(question_folded, ["document", "documents", "paperwork", "bring", "id", "proof of address"]):
            hints.extend(VIETNAMESE_QUERY_HINTS["account_documents"])
        else:
            hints.extend(VIETNAMESE_QUERY_HINTS["account_opening"])

    if _has_any_term(question_folded, ["card", "credit card", "debit card"]):
        if _has_any_term(question_folded, ["annual fee", "fee", "fees", "pricing"]):
            hints.extend(VIETNAMESE_QUERY_HINTS["card_fee"])
        else:
            hints.extend(VIETNAMESE_QUERY_HINTS["cards"])

    if _has_any_term(question_folded, ["saving", "savings", "deposit", "interest rate", "term deposit"]):
        hints.extend(VIETNAMESE_QUERY_HINTS["savings"])

    if _has_any_term(question_folded, ["loan", "mortgage", "repayment", "borrow"]):
        if _has_any_term(question_folded, ["mortgage rate", "mortgage rates", "home loan rate", "current", "latest", "rate"]):
            hints.extend(VIETNAMESE_QUERY_HINTS["mortgage_rates"])
        else:
            hints.extend(VIETNAMESE_QUERY_HINTS["loans"])

    if _has_any_term(question_folded, ["transfer", "wrong transfer", "sent money", "recipient"]):
        if _has_any_term(question_folded, ["international", "abroad", "overseas", "swift", "bic"]):
            hints.extend(VIETNAMESE_QUERY_HINTS["international_transfer"])
        else:
            hints.extend(VIETNAMESE_QUERY_HINTS["transfer"])

    if _has_any_term(question_folded, ["security", "otp", "fraud", "phishing", "suspicious"]):
        hints.extend(VIETNAMESE_QUERY_HINTS["security"])

    if _has_any_term(question_folded, ["app", "online banking", "mobile banking", "internet banking"]):
        hints.extend(VIETNAMESE_QUERY_HINTS["digital"])

    if _has_any_term(question_folded, ["customer service hours", "support hours", "service hours", "business hours", "weekend support", "weekend hours", "contact hours"]):
        hints.extend(VIETNAMESE_QUERY_HINTS["service_hours"])

    deduped = []
    seen = set()
    for hint in hints:
        folded_hint = _fold_text(hint)
        if not folded_hint or folded_hint in seen:
            continue
        seen.add(folded_hint)
        deduped.append(hint)
    return deduped


def _expand_queries(question: str) -> List[str]:
    base = (question or "").strip()
    if not base:
        return []

    official_scope = retrieval_scope_for_question(base) == "official_rag"
    source_tokens = _source_bank_tokens() if official_scope else []
    source_prefix = " ".join(source_tokens).strip()
    vietnamese_hints = _english_to_vietnamese_hints(base) if official_scope else []

    expanded = [base]
    if source_prefix:
        expanded.extend([
            f"{source_prefix} {base}",
            f"{source_prefix} {base} product service",
            f"{source_prefix} {base} Vietnam",
        ])
    elif official_scope:
        expanded.extend([
            f"{base} official bank policy",
            f"{base} vietnam banking",
        ])
    for hint in vietnamese_hints:
        expanded.append(f"{source_prefix} {hint}".strip() if source_prefix else hint)
    if not official_scope:
        expanded.extend([
            f"banking guidance {base}",
            f"consumer guidance {base}",
        ])

    lower = base.lower()
    if any(phrase in lower for phrase in ["annual fee", "annual fees", "card annual fee"]):
        expanded.append(
            f"{source_prefix} annual fee card fee schedule".strip()
            if source_prefix else f"{base} card fee schedule official"
        )
    if any(word in lower for word in ["loan", "mortgage", "vay"]):
        expanded.append(f"{source_prefix} personal loan home loan auto loan".strip() if source_prefix else f"{base} affordability repayment documents")
    if any(phrase in lower for phrase in ["mortgage rate", "mortgage rates", "home loan rate"]):
        expanded.append(
            f"{source_prefix} mortgage rate home loan interest".strip()
            if source_prefix else f"{base} mortgage rate official"
        )
    if any(word in lower for word in ["card", "debit", "credit", "thẻ"]):
        expanded.append(f"{source_prefix} credit card benefits annual fee installment".strip() if source_prefix else f"{base} card security fees controls")
    if any(word in lower for word in ["saving", "savings", "deposit", "tiết kiệm"]):
        expanded.append(f"{source_prefix} savings deposit interest term".strip() if source_prefix else f"{base} term flexibility rate guidance")
    if any(phrase in lower for phrase in ["international transfer", "transfer internationally", "send money abroad", "send money overseas"]) or any(word in lower for word in ["swift", "bic"]):
        expanded.append(
            f"{source_prefix} international transfer swift bic fees limits".strip()
            if source_prefix else f"{base} swift bic fees limits official"
        )
    if any(phrase in lower for phrase in ["customer service hours", "support hours", "service hours", "business hours", "weekend support", "weekend hours", "contact hours"]):
        expanded.append(
            f"{source_prefix} customer service hours branch hotline".strip()
            if source_prefix else f"{base} customer service hours official"
        )
    if any(word in lower for word in ["security", "otp", "fraud", "unauthorized"]):
        expanded.append(f"{source_prefix} security fraud alerts official channels".strip() if source_prefix else f"{base} security alerts report immediately")

    seen = set()
    ordered_queries = []
    for query in expanded:
        query = re.sub(r"\s+", " ", query).strip()
        if not query or query in seen:
            continue
        seen.add(query)
        ordered_queries.append(query)
    return ordered_queries[:6]


def _score_result(question: str, title: str, snippet: str) -> float:
    semantic_query = question
    vietnamese_hints = _english_to_vietnamese_hints(question)
    if vietnamese_hints:
        semantic_query = f"{question} {' '.join(vietnamese_hints)}"

    question_tokens = _tokenize(semantic_query)
    content = f"{title} {snippet}".lower()
    content_tokens = _tokenize(content)
    if not question_tokens:
        return 0.0

    overlap = len(question_tokens & content_tokens)
    coverage = overlap / max(1, len(question_tokens))

    factual_markers = 0
    if re.search(r"\d", content):
        factual_markers += 1
    if "%" in content:
        factual_markers += 1
    if any(marker in content for marker in ["fee", "rate", "security", "report", "documents", "liability", "alerts"]):
        factual_markers += 1

    return coverage + (0.05 * factual_markers)


def search_web(query: str, allowed_domains: tuple, source_scope: str, num_results: int = 5) -> List[Dict]:
    cache_key = f"{query.strip().lower()}::{num_results}::{','.join(allowed_domains)}::{source_scope}"
    cached = _cache_get(_SEARCH_CACHE, cache_key)
    if cached is not None:
        return cached

    if not GOOGLE_API_KEY or not SEARCH_ENGINE_ID or not allowed_domains or not source_scope:
        return []

    url = "https://www.googleapis.com/customsearch/v1"
    site_clause = _build_site_clause(allowed_domains)
    if source_scope == "official_rag":
        source_prefix = " ".join(_source_bank_tokens()).strip()
        scoped_query = f"{source_prefix} {query} {site_clause}".strip()
    else:
        scoped_query = f"{query} {site_clause}".strip()

    params = {
        "key": GOOGLE_API_KEY,
        "cx": SEARCH_ENGINE_ID,
        "q": scoped_query,
        "num": num_results,
    }

    try:
        response = requests.get(url, params=params, timeout=SEARCH_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
        results = []
        for item in data.get("items", []):
            link = item.get("link", "")
            if not _is_trusted_source(link, allowed_domains):
                continue
            domain = urlparse(link).netloc.lower()
            results.append(
                {
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", ""),
                    "link": link,
                    "domain": domain,
                    "source_scope": source_scope,
                }
            )
        _cache_set(_SEARCH_CACHE, cache_key, results)
        return results
    except Exception as e:
        print(f"Search error: {e}")
        return []


def retrieve_context(question: str, max_results: int = 5) -> List[Dict]:
    scope = retrieval_scope_for_question(question)
    cache_key = f"{(question or '').strip().lower()}::{max_results}::{scope or 'none'}"
    cached = _cache_get(_RETRIEVE_CACHE, cache_key)
    if cached is not None:
        return cached

    if not should_retrieve(question):
        return []

    if not scope:
        return []

    allowed_domains = _allowed_domains(question)
    if not allowed_domains:
        return []

    queries = _expand_queries(question)
    if not queries:
        return []

    pooled_results = []
    seen_links = set()

    for query in queries:
        for result in search_web(
            query,
            allowed_domains=allowed_domains,
            source_scope=scope,
            num_results=min(max_results + 1, 8),
        ):
            link = result.get("link", "")
            snippet = (result.get("snippet", "") or "").strip()
            if not link or not snippet or link in seen_links:
                continue
            seen_links.add(link)
            pooled_results.append(result)

    if not pooled_results:
        return []

    reranked_results = sorted(
        pooled_results,
        key=lambda item: _score_result(question, item.get("title", ""), item.get("snippet", "")),
        reverse=True,
    )
    final_results = reranked_results[:max_results]
    _cache_set(_RETRIEVE_CACHE, cache_key, final_results)
    return final_results
