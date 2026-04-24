import re
from typing import Optional, Tuple


ACK_PREFIX_PATTERNS = (
    r"^(?:ok(?:ay)?|thanks|thank you|thx|ty|got it|understood|that'?s all|that is all|bye|goodbye)\b(?P<rest>.*)$",
    r"^(?:cảm ơn|cam on|xong rồi|tạm biệt)\b(?P<rest>.*)$",
)

GREETING_PREFIX_PATTERNS = (
    r"^(?:hi|hello|hey|good morning|good afternoon|good evening)\b(?P<rest>.*)$",
    r"^(?:xin chào|chào)\b(?P<rest>.*)$",
)

SOCIAL_FILLER_PATTERNS = (
    r"there",
    r"again",
    r"everyone",
    r"team",
    r"assistant",
    r"bot",
    r"folks",
    r"friend",
    r"friends",
    r"amazingbank",
    r"amazingbank team",
    r"bank team",
    r"a lot",
    r"so much",
    r"very much",
    r"for the help",
    r"for your help",
    r"for explaining",
    r"for that",
)

SEPARATOR_CHARS = " \t\r\n,;:.!?-_/|()[]{}"
ALNUM_PATTERN = re.compile(r"[a-z0-9]", flags=re.IGNORECASE)


def normalize_turn(text: str) -> str:
    normalized = (text or "").lower().strip()
    normalized = re.sub(r"[“”'`\"]", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _strip_leading_separators(text: str) -> str:
    return (text or "").lstrip(SEPARATOR_CHARS)


def _strip_social_fillers(text: str) -> str:
    remainder = _strip_leading_separators(text)

    while remainder:
        matched = False
        for pattern in SOCIAL_FILLER_PATTERNS:
            fill_match = re.match(rf"^(?:{pattern})\b", remainder, flags=re.IGNORECASE)
            if not fill_match:
                continue
            remainder = _strip_leading_separators(remainder[fill_match.end():])
            matched = True
            break
        if not matched:
            break

    return remainder


def strip_leading_social_prefix(text: str) -> Tuple[Optional[str], str]:
    remainder = normalize_turn(text)
    detected = None

    while remainder:
        matched = False
        for label, patterns in (
            ("ack_only", ACK_PREFIX_PATTERNS),
            ("greeting_only", GREETING_PREFIX_PATTERNS),
        ):
            for pattern in patterns:
                prefix_match = re.match(pattern, remainder, flags=re.IGNORECASE)
                if not prefix_match:
                    continue
                detected = detected or label
                remainder = _strip_social_fillers(prefix_match.group("rest"))
                matched = True
                break
            if matched:
                break

        if not matched:
            break

    return detected, _strip_social_fillers(remainder)


def classify_turn(text: str) -> str:
    normalized = normalize_turn(text)
    if not normalized:
        return "empty"

    if not ALNUM_PATTERN.search(normalized):
        return "unclear"

    social_label, remainder = strip_leading_social_prefix(normalized)
    if social_label and not ALNUM_PATTERN.search(remainder):
        return social_label

    return "substantive"
