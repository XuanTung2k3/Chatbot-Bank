#!/usr/bin/env python3
"""Smoke-test the four deployed chatbot endpoints with a shared QA matrix."""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
import uuid


ENDPOINTS = {
    "finance_emp": {
        "url": "https://m-finance-137003227004.us-central1.run.app",
        "mode": "emp",
        "domain": "finance",
    },
    "finance_non": {
        "url": "https://non-m-finance-137003227004.us-central1.run.app",
        "mode": "non",
        "domain": "finance",
    },
    "spa_emp": {
        "url": "https://emp-spa-137003227004.us-central1.run.app",
        "mode": "emp",
        "domain": "spa",
    },
    "spa_non": {
        "url": "https://non-emp-spa-137003227004.us-central1.run.app",
        "mode": "non",
        "domain": "spa",
    },
}

QUESTIONS = {
    "finance": [
        "Hello",
        "Tell me about card service",
        "I want you talk about loan service",
        "What savings options do you have?",
        "What is the annual fee?",
        "Which is best for me?",
        "Techcombank credit card phone number",
        "Ok thanks",
    ],
    "spa": [
        "Hello",
        "What spa services do you offer?",
        "Tell me about massage services",
        "I want skin care",
        "What are your opening hours?",
        "JW Marriott spa phone number",
        "L'Occitane treatment details",
        "Ok thanks",
    ],
}

NON_EMPATHY_MARKERS = [
    "i hear",
    "i understand",
    "thank you for sharing",
    "happy to help",
    "you are very welcome",
]

EMP_WARMTH_MARKERS = [
    *NON_EMPATHY_MARKERS,
    "thanks for raising",
    "let us make",
    "lovely question",
    "gentle",
    "soothing",
    "restorative",
    "i am here",
    "we can design",
]

EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "]+"
)

LEAK_PATTERNS = [
    r"\btechcombank\b",
    r"\bjw\s*marriott\b",
    r"\bl['’]occitane\b",
    r"\bwellbeing\s*on\s*8\b",
    r"\b(?:\+?84[\s\-.]?)?(?:1800|1900)[\s\-.]?\d{3}[\s\-.]?\d{3}\b",
    r"\b[\w.\-]+@[\w.\-]+\.\w+\b",
]

CLOSER_PATTERNS = [
    r"^(ok|okay|thanks|thank you|thx|ty|that'?s all|that is all|bye)\b",
]

GREETING_PATTERNS = [
    r"^(hi|hello|hey|good morning|good afternoon|good evening)\b",
]


def post_json(url, payload, timeout):
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.time()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    elapsed_ms = int((time.time() - started) * 1000)
    return json.loads(body), elapsed_ms


def is_closer(question):
    normalized = question.strip().lower()
    return any(re.search(pattern, normalized) for pattern in CLOSER_PATTERNS)


def is_greeting(question):
    normalized = question.strip().lower()
    return any(re.search(pattern, normalized) for pattern in GREETING_PATTERNS)


def assert_response(name, question, response):
    failures = []
    text = (response.get("response") or "").strip()
    lowered = text.lower()
    endpoint = ENDPOINTS[name]

    if not text:
        failures.append("empty response")
    if "could not process" in lowered:
        failures.append("contains blocked fallback phrase")
    if (is_closer(question) or is_greeting(question)) and "next step:" in lowered:
        failures.append("non-actionable input contains confusing Next step prompt")
    for pattern in LEAK_PATTERNS:
        if re.search(pattern, lowered, flags=re.IGNORECASE):
            failures.append(f"brand/contact leak: {pattern}")
    if endpoint["mode"] == "non":
        if EMOJI_RE.search(text):
            failures.append("non-em response contains emoji")
        if any(marker in lowered for marker in NON_EMPATHY_MARKERS):
            failures.append("non-em response contains empathy marker")
    if endpoint["mode"] == "emp" and not is_closer(question):
        if not EMOJI_RE.search(text):
            failures.append("em response missing emotion icon")
        if not any(marker in lowered for marker in EMP_WARMTH_MARKERS):
            failures.append("em response missing warmth marker")

    return failures


def main():
    parser = argparse.ArgumentParser(description="Run chatbot QA smoke tests.")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        print(json.dumps({"endpoints": ENDPOINTS, "questions": QUESTIONS}, indent=2))
        return 0

    all_failures = []
    for name, endpoint in ENDPOINTS.items():
        user_hash = f"qa_{name}_{uuid.uuid4().hex[:10]}"
        try:
            post_json(endpoint["url"], {"question": "", "userHash": user_hash, "initConversation": True}, args.timeout)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            all_failures.append(f"{name} :: initConversation :: request failed: {exc}")
            continue

        for question in QUESTIONS[endpoint["domain"]]:
            try:
                response, elapsed_ms = post_json(
                    endpoint["url"],
                    {"question": question, "userHash": user_hash},
                    args.timeout,
                )
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                all_failures.append(f"{name} :: {question} :: request failed: {exc}")
                continue

            failures = assert_response(name, question, response)
            status = "FAIL" if failures else "PASS"
            print(f"{status} {name} [{elapsed_ms}ms] {question} -> {response.get('response', '')}")
            for failure in failures:
                all_failures.append(f"{name} :: {question} :: {failure}")

    if all_failures:
        print("\nFailures:")
        for failure in all_failures:
            print(f"- {failure}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
