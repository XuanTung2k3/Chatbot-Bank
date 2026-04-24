#!/usr/bin/env python3
"""Hybrid English-only test flow utilities for the Finance empathetic and non-empathetic chatbots.

This module provides two CLI subcommands:

1. prepare-sheet
   Generate a CSV evaluation sheet for manual website testing and API comparisons.

2. api-batch
   Run the canonical English corpus against both live endpoints and export
   structured results with first-pass verdicts and suspected failure layers.

The tooling uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Dict, Iterable, List, Sequence


HERE = Path(__file__).resolve().parent
FINANCE_ROOT = HERE.parent
REPO_ROOT = FINANCE_ROOT.parent
CORPUS_PATH = HERE / "chatbot_english_test_corpus.json"
DEFAULT_OUTPUT_DIR = HERE / "output"

ENDPOINTS = {
    "empathetic": "https://m-finance-137003227004.us-central1.run.app",
    "nonempathetic": "https://non-m-finance-137003227004.us-central1.run.app",
}

WEBSITE_TARGETS = {
    "empathetic": "https://vincent-bank-empathetic.web.app/",
    "nonempathetic": "https://vincent-bank-non-empathetic.web.app/",
}

FRONTEND_ENTRYPOINTS = {
    "empathetic": [
        "Finance/Empathetic/Frontend/index.html",
        "Finance/Empathetic/empathetic-standalone.html",
    ],
    "nonempathetic": [
        "Finance/NonEmpathetic/Frontend/index.html",
        "Finance/NonEmpathetic/non-empathetic-standalone.html",
    ],
}

GREETING_FALLBACK_MARKERS = (
    "provide an amazingbank service or question to continue",
    "ask a question to continue",
    "whenever you are ready",
)

SOURCE_BANK_MARKERS = tuple(
    marker.lower()
    for marker in {
        os.getenv("SOURCE_BANK_NAME", "Techcombank"),
        os.getenv("SOURCE_BANK_SHORT_NAME", "TCB"),
    }
    if marker.strip()
)

EMPATHY_MARKERS = (
    "i hear you",
    "i understand",
    "happy to help",
    "sorry you are dealing with",
    "sorry you're dealing with",
    "thank you for sharing",
)

VIETNAMESE_CHAR_PATTERN = re.compile(
    r"[a-zA-Z]*[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩị"
    r"óòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]+[a-zA-Z]*"
)

VIETNAMESE_WORD_HINTS = {
    "gio",
    "ngan",
    "hang",
    "khoan",
    "lai",
    "suat",
    "phi",
    "vay",
    "mat",
    "khach",
    "tro",
    "chuyen",
    "tien",
    "giay",
    "thu",
    "den",
    "sau",
}

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "be",
    "can",
    "do",
    "does",
    "for",
    "how",
    "i",
    "if",
    "in",
    "is",
    "it",
    "my",
    "of",
    "on",
    "or",
    "the",
    "to",
    "what",
    "which",
    "with",
    "you",
    "your",
    "amazingbank",
}

CSV_FIELDS = [
    "run_id",
    "channel",
    "mode",
    "endpoint",
    "frontend_entrypoints",
    "topic_id",
    "topic_label",
    "question_id",
    "question",
    "variant_type",
    "expectation_type",
    "expected_answer_core",
    "official_reference_url",
    "website_session_group",
    "website_session_order",
    "session_id",
    "response",
    "response_mode",
    "turn_classification",
    "grounding_scope",
    "cache_hit",
    "cache_version",
    "verdict",
    "error_type",
    "suspected_layer",
    "relevance_score",
    "notes",
]

QUESTION_FILE_RESULT_FIELDS = [
    "run_id",
    "mode",
    "requested_target",
    "endpoint",
    "section_index",
    "section_title",
    "question_index",
    "question_id",
    "question",
    "session_id",
    "response",
    "response_mode",
    "turn_classification",
    "grounding_scope",
    "cache_hit",
    "cache_version",
    "attempt_count",
    "transport_error",
    "notes",
]

QUESTION_FILE_GRADED_FIELDS = QUESTION_FILE_RESULT_FIELDS + [
    "topic_id",
    "topic_label",
    "variant_type",
    "expectation_type",
    "expected_answer_core",
    "official_reference_url",
    "verdict",
    "error_type",
    "suspected_layer",
    "relevance_score",
]


def load_corpus(path: Path = CORPUS_PATH) -> Dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def parse_questions_file(path: Path) -> List[Dict[str, str]]:
    records: List[Dict[str, str]] = []
    section_index = "0"
    section_title = "Ungrouped"
    question_index = 0

    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue

            section_match = re.match(r"^(\d+)\.\s+(.+)$", line)
            if section_match and not line.endswith("?"):
                section_index = section_match.group(1)
                section_title = section_match.group(2).strip()
                continue

            question_index += 1
            records.append(
                {
                    "section_index": section_index,
                    "section_title": section_title,
                    "question_index": str(question_index),
                    "question_id": f"q{question_index:03d}",
                    "question": line,
                }
            )

    return records


def _extract_api_endpoint_from_text(text: str) -> str:
    match = re.search(r'(?:DEFAULT_API_ENDPOINT|API_ENDPOINT)\s*=\s*"([^"]+)"', text or "")
    if match:
        return match.group(1).rstrip("/")

    fallback = re.search(r"https://[a-z0-9.-]+\.run\.app", text or "", flags=re.IGNORECASE)
    return fallback.group(0).rstrip("/") if fallback else ""


def _extract_script_sources(text: str) -> List[str]:
    return re.findall(r'<script[^>]+src="([^"]+)"', text or "", flags=re.IGNORECASE)


def _read_text_from_url(url: str, timeout_sec: int = 10) -> str:
    with urllib.request.urlopen(url, timeout=timeout_sec) as response:
        return response.read().decode("utf-8", errors="replace")


def extract_endpoint_from_frontend(frontend_path: str) -> str:
    file_path = REPO_ROOT / frontend_path
    try:
        content = file_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""

    endpoint = _extract_api_endpoint_from_text(content)
    if endpoint:
        return endpoint

    for script_src in _extract_script_sources(content):
        if script_src.startswith(("http://", "https://")):
            continue
        script_path = (file_path.parent / script_src).resolve()
        if not script_path.exists():
            continue
        endpoint = _extract_api_endpoint_from_text(script_path.read_text(encoding="utf-8"))
        if endpoint:
            return endpoint

    return ""


def resolve_endpoint_target(target: str, timeout_sec: int = 10) -> str:
    normalized_target = (target or "").strip()
    if not normalized_target:
        return ""
    if ".run.app" in normalized_target:
        return normalized_target.rstrip("/")

    try:
        html = _read_text_from_url(normalized_target, timeout_sec=timeout_sec)
    except Exception:
        return ""

    endpoint = _extract_api_endpoint_from_text(html)
    if endpoint:
        return endpoint

    for script_src in _extract_script_sources(html):
        script_url = urllib.parse.urljoin(normalized_target, script_src)
        try:
            script_text = _read_text_from_url(script_url, timeout_sec=timeout_sec)
        except Exception:
            continue
        endpoint = _extract_api_endpoint_from_text(script_text)
        if endpoint:
            return endpoint

    return ""


def load_endpoints(overrides: Dict[str, str] | None = None) -> Dict[str, str]:
    endpoints = dict(ENDPOINTS)

    for mode, entrypoints in FRONTEND_ENTRYPOINTS.items():
        for frontend in entrypoints:
            endpoint = extract_endpoint_from_frontend(frontend)
            if endpoint:
                endpoints[mode] = endpoint
                break

    if overrides:
        for mode, target in overrides.items():
            endpoint = resolve_endpoint_target(target)
            if endpoint:
                endpoints[mode] = endpoint

    return endpoints


def _topic_lookup(corpus: Dict) -> Dict[str, Dict[str, str]]:
    return {
        bucket["topic_id"]: {
            "topic_label": bucket["topic_label"],
            "website_session_order": index,
        }
        for index, bucket in enumerate(corpus["topic_buckets"], start=1)
    }


def _record_allowed(record: Dict[str, str], topic_ids: Sequence[str], variant_types: Sequence[str]) -> bool:
    if topic_ids and record["topic_id"] not in topic_ids:
        return False
    if variant_types and record["variant_type"] not in variant_types:
        return False
    return True


def iter_question_records(
    corpus: Dict,
    include_mixed_social: bool = True,
    topic_ids: Sequence[str] = (),
    variant_types: Sequence[str] = (),
) -> Iterable[Dict[str, str]]:
    topic_meta = _topic_lookup(corpus)

    for index, bucket in enumerate(corpus["topic_buckets"], start=1):
        for question in bucket["questions"]:
            record = {
                "topic_id": bucket["topic_id"],
                "topic_label": bucket["topic_label"],
                "question_id": question["id"],
                "question": question["question"],
                "variant_type": question["variant_type"],
                "expectation_type": question["expectation_type"],
                "expected_answer_core": question["expected_answer_core"],
                "official_reference_url": question.get("official_reference_url", ""),
                "website_session_group": bucket["topic_id"],
                "website_session_order": str(index),
            }
            if _record_allowed(record, topic_ids, variant_types):
                yield record

    if not include_mixed_social:
        return

    for question in corpus.get("mixed_social_regression", []):
        meta = topic_meta.get(question["topic_id"], {})
        record = {
            "topic_id": question["topic_id"],
            "topic_label": meta.get("topic_label", question["topic_id"]),
            "question_id": question["id"],
            "question": question["question"],
            "variant_type": question["variant_type"],
            "expectation_type": question["expectation_type"],
            "expected_answer_core": question["expected_answer_core"],
            "official_reference_url": question.get("official_reference_url", ""),
            "website_session_group": "mixed_social_regression",
            "website_session_order": str(len(corpus["topic_buckets"]) + 1),
        }
        if _record_allowed(record, topic_ids, variant_types):
            yield record


def build_question_record_lookup(corpus: Dict, include_mixed_social: bool = True) -> Dict[str, Dict[str, str]]:
    lookup: Dict[str, Dict[str, str]] = {}
    for record in iter_question_records(corpus, include_mixed_social=include_mixed_social):
        lookup.setdefault(normalize_question_key(record["question"]), dict(record))
    return lookup


def build_sheet_rows(
    corpus: Dict,
    modes: Sequence[str],
    channels: Sequence[str],
    include_mixed_social: bool = True,
    run_id: str = "",
    topic_ids: Sequence[str] = (),
    variant_types: Sequence[str] = (),
) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    endpoints = load_endpoints()
    records = list(
        iter_question_records(
            corpus,
            include_mixed_social=include_mixed_social,
            topic_ids=topic_ids,
            variant_types=variant_types,
        )
    )

    for channel in channels:
        for mode in modes:
            endpoint = endpoints[mode] if channel == "api" else ""
            frontend_paths = " | ".join(FRONTEND_ENTRYPOINTS[mode]) if channel == "website" else ""
            for record in records:
                row = {field: "" for field in CSV_FIELDS}
                row.update(record)
                row["run_id"] = run_id
                row["channel"] = channel
                row["mode"] = mode
                row["endpoint"] = endpoint
                row["frontend_entrypoints"] = frontend_paths
                rows.append(row)
    return rows


def write_csv(path: Path, rows: Sequence[Dict[str, str]], fieldnames: Sequence[str] = CSV_FIELDS) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def write_json(path: Path, payload: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def post_json(url: str, payload: Dict, timeout: int = 25) -> Dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw)


def normalize_tokens(text: str) -> List[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+", (text or "").lower())
        if len(token) > 1 and token not in STOPWORDS
    ]


def normalize_question_key(text: str) -> str:
    normalized = (text or "").strip().lower()
    normalized = normalized.replace("’", "'").replace("“", '"').replace("”", '"')
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def keyword_overlap_score(question: str, response: str) -> float:
    q_tokens = set(normalize_tokens(question))
    r_tokens = set(normalize_tokens(response))
    if not q_tokens:
        return 0.0
    return len(q_tokens & r_tokens) / max(1, len(q_tokens))


def is_likely_english(text: str) -> bool:
    content = (text or "").strip()
    if not content:
        return False
    if VIETNAMESE_CHAR_PATTERN.search(content):
        return False
    tokens = [token.lower() for token in re.findall(r"[a-zA-Z]+", content)]
    vietnamese_hits = sum(token in VIETNAMESE_WORD_HINTS for token in tokens)
    return not (vietnamese_hits >= 3 and vietnamese_hits >= max(3, len(tokens) // 6))


def contains_source_bank_leak(text: str) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in SOURCE_BANK_MARKERS)


def contains_fallback_marker(text: str) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in GREETING_FALLBACK_MARKERS)


def has_specific_claim(text: str) -> bool:
    lowered = (text or "").lower()
    if re.search(r"\b\d+(?:[.,]\d+)?\b", lowered):
        return True
    if "%" in lowered:
        return True
    return any(symbol in lowered for symbol in ("$", "usd", "vnd"))


def contains_empathy(text: str) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in EMPATHY_MARKERS)


def expected_grounding(expectation_type: str) -> str:
    if expectation_type == "playbook_expected":
        return "playbook"
    if expectation_type == "official_rag_expected":
        return "official_rag"
    if expectation_type == "live_or_strict_grounding":
        return "official_rag_or_live_fallback"
    if expectation_type == "public_guidance_acceptable":
        return "public_guidance_or_official_rag"
    return "model_only_acceptable"


def evaluate_api_result(
    mode: str,
    record: Dict[str, str],
    api_response: Dict,
    endpoint: str,
    transport_error: str = "",
) -> Dict[str, str]:
    response = api_response.get("response", "") if api_response else ""
    response_mode = api_response.get("response_mode", "") if api_response else ""
    turn_classification = api_response.get("turn_classification", "") if api_response else ""
    grounding_scope = api_response.get("grounding_scope", "") if api_response else ""
    cache_hit = str(api_response.get("cache_hit", "")) if api_response else ""
    cache_version = api_response.get("cache_version", "") if api_response else ""
    session_id = api_response.get("userHash", "") if api_response else ""

    notes: List[str] = []
    verdict = "Pass"
    error_type = ""
    suspected_layer = ""

    relevance = keyword_overlap_score(record["question"], response)

    if transport_error:
        verdict = "Fail"
        error_type = "transport_error"
        suspected_layer = "endpoint_or_network"
        notes.append(transport_error)
    elif not response.strip():
        verdict = "Fail"
        error_type = "empty_response"
        suspected_layer = "backend_generation_or_transport"
    elif turn_classification and turn_classification != "substantive":
        verdict = "Fail"
        error_type = "misclassified_turn"
        suspected_layer = "turn_classifier_or_routing"
        notes.append(f"turn_classification={turn_classification}")
    elif contains_fallback_marker(response):
        verdict = "Fail"
        error_type = "fallback_ignored_question"
        suspected_layer = "turn_classifier_or_policy_fallback"
    elif not is_likely_english(response):
        verdict = "Fail"
        error_type = "wrong_language"
        suspected_layer = "prompt_or_finalizer"
    elif contains_source_bank_leak(response):
        verdict = "Fail"
        error_type = "source_brand_leak"
        suspected_layer = "prompt_or_sanitizer"
    else:
        expectation_type = record["expectation_type"]

        if relevance < 0.10:
            verdict = "Fail"
            error_type = "not_related"
            suspected_layer = "playbook_or_rag_synthesis"
            notes.append(f"relevance={relevance:.2f}")
        elif expectation_type == "live_or_strict_grounding":
            if grounding_scope not in {"official_rag", "live_fallback"}:
                if has_specific_claim(response):
                    verdict = "Fail"
                    error_type = "unsupported_specific_claim"
                    suspected_layer = "grounding_policy_or_generation"
                else:
                    verdict = "Weak pass"
                    error_type = "ungrounded_bank_specific_answer"
                    suspected_layer = "retrieval_gating_or_strict_grounding"
                notes.append(f"grounding_scope={grounding_scope or 'missing'}")
        elif expectation_type == "official_rag_expected" and grounding_scope == "model_only":
            verdict = "Weak pass"
            error_type = "missing_official_grounding"
            suspected_layer = "retrieval_gating_or_query_expansion"
            notes.append("bank-specific answer came from model_only")
        elif expectation_type == "playbook_expected" and grounding_scope not in {"playbook", "official_rag"}:
            verdict = "Weak pass"
            error_type = "playbook_not_used"
            suspected_layer = "playbook_matching_or_routing"
            notes.append(f"grounding_scope={grounding_scope or 'missing'}")
        elif expectation_type == "public_guidance_acceptable" and grounding_scope == "model_only":
            verdict = "Weak pass"
            error_type = "no_grounding_for_guidance"
            suspected_layer = "retrieval_policy"
            notes.append("public-guidance answer came from model_only")

        if mode == "nonempathetic" and verdict != "Fail" and contains_empathy(response):
            verdict = "Weak pass"
            error_type = error_type or "style_mode_mismatch"
            suspected_layer = suspected_layer or "prompt_or_finalizer_style"
            notes.append("nonempathetic response includes empathy markers")

    if verdict != "Pass" and cache_hit == "True":
        notes.append("cache-contamination-candidate")

    row = {field: "" for field in CSV_FIELDS}
    row.update(record)
    row["channel"] = "api"
    row["mode"] = mode
    row["endpoint"] = endpoint
    row["response"] = response
    row["response_mode"] = response_mode
    row["turn_classification"] = turn_classification
    row["grounding_scope"] = grounding_scope
    row["cache_hit"] = cache_hit
    row["cache_version"] = cache_version
    row["session_id"] = session_id
    row["verdict"] = verdict
    row["error_type"] = error_type
    row["suspected_layer"] = suspected_layer
    row["relevance_score"] = f"{relevance:.2f}"
    row["notes"] = "; ".join(notes)
    return row


def summarize_rows(rows: Sequence[Dict[str, str]]) -> Dict[str, Dict[str, int]]:
    summary: Dict[str, Dict[str, int]] = {}
    for row in rows:
        mode = row["mode"]
        verdict = row["verdict"] or "Unscored"
        summary.setdefault(mode, {})
        summary[mode][verdict] = summary[mode].get(verdict, 0) + 1
    return summary


def run_api_batch(
    corpus: Dict,
    modes: Sequence[str],
    include_mixed_social: bool = True,
    delay_ms: int = 0,
    topic_ids: Sequence[str] = (),
    variant_types: Sequence[str] = (),
    bypass_cache: bool = False,
    timeout_sec: int = 25,
    endpoint_overrides: Dict[str, str] | None = None,
) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    endpoints = load_endpoints(endpoint_overrides)
    records = list(
        iter_question_records(
            corpus,
            include_mixed_social=include_mixed_social,
            topic_ids=topic_ids,
            variant_types=variant_types,
        )
    )

    for mode in modes:
        endpoint = endpoints[mode]
        for record in records:
            user_hash = str(uuid.uuid4())
            transport_error = ""
            answer_response: Dict = {}
            try:
                bootstrap_payload = {"userHash": user_hash, "question": "", "initConversation": True}
                answer_payload = {"userHash": user_hash, "question": record["question"]}
                if bypass_cache:
                    bootstrap_payload["bypassCache"] = True
                    answer_payload["bypassCache"] = True
                post_json(endpoint, bootstrap_payload, timeout=timeout_sec)
                answer_response = post_json(endpoint, answer_payload, timeout=timeout_sec)
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, socket.timeout, json.JSONDecodeError) as exc:
                transport_error = str(exc)
            row = evaluate_api_result(mode, record, answer_response, endpoint, transport_error=transport_error)
            rows.append(row)
            if delay_ms > 0:
                time.sleep(delay_ms / 1000.0)

    return rows


def run_api_questions_file(
    questions: Sequence[Dict[str, str]],
    modes: Sequence[str],
    delay_ms: int = 0,
    timeout_sec: int = 25,
    bypass_cache: bool = False,
    endpoint_overrides: Dict[str, str] | None = None,
    max_attempts: int = 3,
    retry_delay_ms: int = 1000,
) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    endpoints = load_endpoints(endpoint_overrides)

    for mode in modes:
        endpoint = endpoints[mode]
        requested_target = (endpoint_overrides or {}).get(mode, "") or WEBSITE_TARGETS.get(mode, "")
        for item in questions:
            transport_error = ""
            answer_response: Dict = {}
            response = ""
            attempt_count = 0

            for attempt in range(1, max(1, max_attempts) + 1):
                attempt_count = attempt
                user_hash = str(uuid.uuid4())
                try:
                    answer_payload = {"userHash": user_hash, "question": item["question"], "initConversation": True}
                    if bypass_cache:
                        answer_payload["bypassCache"] = True
                    answer_response = post_json(endpoint, answer_payload, timeout=timeout_sec)
                    response = answer_response.get("response", "") if answer_response else ""
                    transport_error = ""
                    if response.strip():
                        break
                    transport_error = "empty_response"
                except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, socket.timeout, json.JSONDecodeError) as exc:
                    transport_error = str(exc)
                    answer_response = {}
                    response = ""

                if attempt < max(1, max_attempts):
                    time.sleep(max(0, retry_delay_ms) / 1000.0)

            row = {field: "" for field in QUESTION_FILE_RESULT_FIELDS}
            row["mode"] = mode
            row["requested_target"] = requested_target or endpoint
            row["endpoint"] = endpoint
            row["section_index"] = item["section_index"]
            row["section_title"] = item["section_title"]
            row["question_index"] = item["question_index"]
            row["question_id"] = item["question_id"]
            row["question"] = item["question"]
            row["session_id"] = answer_response.get("userHash", "") if answer_response else ""
            row["response"] = response
            row["response_mode"] = answer_response.get("response_mode", "") if answer_response else ""
            row["turn_classification"] = answer_response.get("turn_classification", "") if answer_response else ""
            row["grounding_scope"] = answer_response.get("grounding_scope", "") if answer_response else ""
            row["cache_hit"] = str(answer_response.get("cache_hit", "")) if answer_response else ""
            row["cache_version"] = answer_response.get("cache_version", "") if answer_response else ""
            row["attempt_count"] = str(attempt_count)
            row["transport_error"] = "" if transport_error == "empty_response" else transport_error

            notes: List[str] = []
            if attempt_count > 1:
                notes.append(f"attempts={attempt_count}")
            if transport_error == "empty_response":
                notes.append("empty_response")
            elif not transport_error and not response.strip():
                notes.append("empty_response")
            if row["turn_classification"] and row["turn_classification"] != "substantive":
                notes.append(f"non_substantive_turn={row['turn_classification']}")
            row["notes"] = "; ".join(notes)
            rows.append(row)

            if delay_ms > 0:
                time.sleep(delay_ms / 1000.0)

    return rows


def summarize_question_file_rows(rows: Sequence[Dict[str, str]]) -> Dict[str, Dict[str, int]]:
    summary: Dict[str, Dict[str, int]] = {}
    for row in rows:
        mode = row["mode"] or "unknown"
        stats = summary.setdefault(mode, {"total": 0, "transport_error": 0, "empty_response": 0, "non_substantive_turn": 0})
        stats["total"] += 1
        if row.get("transport_error"):
            stats["transport_error"] += 1
        if not row.get("response", "").strip():
            stats["empty_response"] += 1
        if row.get("turn_classification") and row.get("turn_classification") != "substantive":
            stats["non_substantive_turn"] += 1
    return summary


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def merge_notes(*parts: str) -> str:
    merged: List[str] = []
    for part in parts:
        if not part:
            continue
        for chunk in [piece.strip() for piece in part.split(";")]:
            if chunk and chunk not in merged:
                merged.append(chunk)
    return "; ".join(merged)


def fallback_question_record(row: Dict[str, str]) -> Dict[str, str]:
    return {
        "topic_id": "unmapped_question_file",
        "topic_label": row.get("section_title", "Unmapped question file"),
        "question_id": row.get("question_id", ""),
        "question": row.get("question", ""),
        "variant_type": "canonical",
        "expectation_type": "model_only_acceptable",
        "expected_answer_core": "",
        "official_reference_url": "",
        "website_session_group": row.get("section_title", ""),
        "website_session_order": row.get("section_index", ""),
    }


def grade_question_file_rows(rows: Sequence[Dict[str, str]], corpus: Dict) -> List[Dict[str, str]]:
    lookup = build_question_record_lookup(corpus, include_mixed_social=True)
    graded_rows: List[Dict[str, str]] = []

    for raw in rows:
        record = lookup.get(normalize_question_key(raw.get("question", "")))
        unmatched = record is None
        record = dict(record or fallback_question_record(raw))

        api_response = {
            "response": raw.get("response", ""),
            "response_mode": raw.get("response_mode", ""),
            "turn_classification": raw.get("turn_classification", ""),
            "grounding_scope": raw.get("grounding_scope", ""),
            "cache_hit": raw.get("cache_hit", ""),
            "cache_version": raw.get("cache_version", ""),
            "userHash": raw.get("session_id", ""),
        }
        graded = evaluate_api_result(
            raw.get("mode", ""),
            record,
            api_response,
            raw.get("endpoint", ""),
            transport_error=raw.get("transport_error", ""),
        )

        row = {field: "" for field in QUESTION_FILE_GRADED_FIELDS}
        for field in QUESTION_FILE_RESULT_FIELDS:
            row[field] = raw.get(field, "")
        for field in (
            "topic_id",
            "topic_label",
            "variant_type",
            "expectation_type",
            "expected_answer_core",
            "official_reference_url",
            "verdict",
            "error_type",
            "suspected_layer",
            "relevance_score",
        ):
            row[field] = graded.get(field, record.get(field, ""))

        row["notes"] = merge_notes(
            raw.get("notes", ""),
            graded.get("notes", ""),
            "unmatched_question_in_corpus_lookup" if unmatched else "",
        )
        graded_rows.append(row)

    return graded_rows


def write_question_file_grading_outputs(
    output_dir: Path,
    run_id: str,
    questions_file: Path,
    requested_targets: Dict[str, str],
    resolved_endpoints: Dict[str, str],
    graded_rows: Sequence[Dict[str, str]],
) -> None:
    graded_csv_path = output_dir / "question_file_results_graded.csv"
    graded_json_path = output_dir / "question_file_results_graded.json"
    graded_summary_path = output_dir / "question_file_grading_summary.json"

    write_csv(graded_csv_path, graded_rows, fieldnames=QUESTION_FILE_GRADED_FIELDS)
    write_json(
        graded_json_path,
        {
            "run_id": run_id,
            "questions_file": str(questions_file),
            "requested_targets": requested_targets,
            "resolved_endpoints": resolved_endpoints,
            "rows": list(graded_rows),
        },
    )
    write_json(
        graded_summary_path,
        {
            "run_id": run_id,
            "questions_file": str(questions_file),
            "requested_targets": requested_targets,
            "resolved_endpoints": resolved_endpoints,
            "summary": summarize_rows(graded_rows),
        },
    )


def command_prepare_sheet(args: argparse.Namespace) -> int:
    corpus = load_corpus()
    run_id = args.run_id or dt.datetime.now().strftime("sheet_%Y%m%d_%H%M%S")
    rows = build_sheet_rows(
        corpus,
        modes=args.modes,
        channels=args.channels,
        include_mixed_social=not args.no_mixed_social,
        run_id=run_id,
        topic_ids=args.topic_ids,
        variant_types=args.variant_types,
    )
    output_path = Path(args.output)
    write_csv(output_path, rows)
    print(f"Wrote {len(rows)} rows to {output_path}")
    return 0


def command_api_batch(args: argparse.Namespace) -> int:
    corpus = load_corpus()
    run_id = args.run_id or dt.datetime.now().strftime("batch_%Y%m%d_%H%M%S")
    endpoint_overrides = {
        "empathetic": args.empathetic_url,
        "nonempathetic": args.nonempathetic_url,
    }
    rows = run_api_batch(
        corpus,
        modes=args.modes,
        include_mixed_social=not args.no_mixed_social,
        delay_ms=args.delay_ms,
        topic_ids=args.topic_ids,
        variant_types=args.variant_types,
        bypass_cache=args.bypass_cache,
        timeout_sec=args.timeout_sec,
        endpoint_overrides=endpoint_overrides,
    )

    output_dir = Path(args.output_dir or (DEFAULT_OUTPUT_DIR / run_id))
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "api_batch_results.csv"
    json_path = output_dir / "api_batch_results.json"
    summary_path = output_dir / "api_batch_summary.json"

    for row in rows:
        row["run_id"] = run_id

    write_csv(csv_path, rows)
    write_json(
        json_path,
        {
            "run_id": run_id,
            "resolved_endpoints": load_endpoints(endpoint_overrides),
            "rows": rows,
        },
    )
    summary = summarize_rows(rows)
    write_json(summary_path, {"run_id": run_id, "summary": summary})

    print(f"Wrote {len(rows)} API result rows to {csv_path}")
    for mode, verdict_counts in summary.items():
        counts = ", ".join(f"{verdict}={count}" for verdict, count in sorted(verdict_counts.items()))
        print(f"{mode}: {counts}")
    return 0


def command_api_file(args: argparse.Namespace) -> int:
    run_id = args.run_id or dt.datetime.now().strftime("qfile_%Y%m%d_%H%M%S")
    questions_file = Path(args.questions_file)
    if not questions_file.is_absolute():
        questions_file = REPO_ROOT / questions_file

    corpus = load_corpus()
    questions = parse_questions_file(questions_file)
    endpoint_overrides = {
        "empathetic": args.empathetic_url,
        "nonempathetic": args.nonempathetic_url,
    }
    resolved_endpoints = load_endpoints(endpoint_overrides)
    rows = run_api_questions_file(
        questions=questions,
        modes=args.modes,
        delay_ms=args.delay_ms,
        timeout_sec=args.timeout_sec,
        bypass_cache=args.bypass_cache,
        endpoint_overrides=endpoint_overrides,
        max_attempts=args.max_attempts,
        retry_delay_ms=args.retry_delay_ms,
    )

    for row in rows:
        row["run_id"] = run_id

    output_dir = Path(args.output_dir or (DEFAULT_OUTPUT_DIR / run_id))
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "question_file_results.csv"
    json_path = output_dir / "question_file_results.json"
    summary_path = output_dir / "question_file_summary.json"
    requested_targets = {
        "empathetic": endpoint_overrides.get("empathetic") or WEBSITE_TARGETS["empathetic"],
        "nonempathetic": endpoint_overrides.get("nonempathetic") or WEBSITE_TARGETS["nonempathetic"],
    }

    write_csv(csv_path, rows, fieldnames=QUESTION_FILE_RESULT_FIELDS)
    write_json(
        json_path,
        {
            "run_id": run_id,
            "questions_file": str(questions_file),
            "requested_targets": requested_targets,
            "resolved_endpoints": resolved_endpoints,
            "rows": rows,
        },
    )
    write_json(
        summary_path,
        {
            "run_id": run_id,
            "questions_file": str(questions_file),
            "requested_targets": requested_targets,
            "resolved_endpoints": resolved_endpoints,
            "summary": summarize_question_file_rows(rows),
        },
    )
    graded_rows = grade_question_file_rows(rows, corpus)
    write_question_file_grading_outputs(
        output_dir=output_dir,
        run_id=run_id,
        questions_file=questions_file,
        requested_targets=requested_targets,
        resolved_endpoints=resolved_endpoints,
        graded_rows=graded_rows,
    )

    print(f"Wrote {len(rows)} question-file API result rows to {csv_path}")
    print(f"Wrote summary to {summary_path}")
    print(f"Wrote graded results to {output_dir / 'question_file_results_graded.csv'}")
    return 0


def command_grade_file(args: argparse.Namespace) -> int:
    input_csv = Path(args.input_csv)
    if not input_csv.is_absolute():
        input_csv = REPO_ROOT / input_csv

    corpus = load_corpus()
    raw_rows = read_csv_rows(input_csv)
    graded_rows = grade_question_file_rows(raw_rows, corpus)

    run_id = args.run_id or (graded_rows[0].get("run_id", "") if graded_rows else "")
    questions_file = Path(args.questions_file)
    if not questions_file.is_absolute():
        questions_file = REPO_ROOT / questions_file

    requested_targets = {}
    resolved_endpoints = {}
    for mode in ("empathetic", "nonempathetic"):
        mode_rows = [row for row in raw_rows if row.get("mode") == mode]
        requested_targets[mode] = mode_rows[0].get("requested_target", "") if mode_rows else ""
        resolved_endpoints[mode] = mode_rows[0].get("endpoint", "") if mode_rows else ""

    output_dir = Path(args.output_dir) if args.output_dir else input_csv.parent
    if not output_dir.is_absolute():
        output_dir = REPO_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    write_question_file_grading_outputs(
        output_dir=output_dir,
        run_id=run_id,
        questions_file=questions_file,
        requested_targets=requested_targets,
        resolved_endpoints=resolved_endpoints,
        graded_rows=graded_rows,
    )

    print(f"Wrote graded question-file results to {output_dir / 'question_file_results_graded.csv'}")
    print(f"Wrote grading summary to {output_dir / 'question_file_grading_summary.json'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="English-only chatbot test flow utilities.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sheet_parser = subparsers.add_parser("prepare-sheet", help="Generate a manual evaluation CSV template.")
    sheet_parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_DIR / "chatbot_evaluation_sheet_template.csv"),
        help="CSV path for the generated evaluation sheet.",
    )
    sheet_parser.add_argument(
        "--modes",
        nargs="+",
        choices=sorted(ENDPOINTS.keys()),
        default=["empathetic", "nonempathetic"],
        help="Chatbot modes to include in the sheet.",
    )
    sheet_parser.add_argument(
        "--channels",
        nargs="+",
        choices=["website", "api"],
        default=["website", "api"],
        help="Testing channels to include in the sheet.",
    )
    sheet_parser.add_argument(
        "--no-mixed-social",
        action="store_true",
        help="Exclude the mixed-social regression prompts.",
    )
    sheet_parser.add_argument("--run-id", default="", help="Optional run identifier to embed in the sheet.")
    sheet_parser.add_argument(
        "--topic-ids",
        nargs="+",
        default=[],
        help="Optional subset of topic IDs to include.",
    )
    sheet_parser.add_argument(
        "--variant-types",
        nargs="+",
        choices=["canonical", "mixed_social"],
        default=[],
        help="Optional subset of variant types to include.",
    )
    sheet_parser.set_defaults(func=command_prepare_sheet)

    batch_parser = subparsers.add_parser("api-batch", help="Run the live API batch diagnosis.")
    batch_parser.add_argument(
        "--output-dir",
        default="",
        help="Directory for batch CSV/JSON outputs. Defaults to Finance/tests/output/<timestamp>/",
    )
    batch_parser.add_argument(
        "--modes",
        nargs="+",
        choices=sorted(ENDPOINTS.keys()),
        default=["empathetic", "nonempathetic"],
        help="Chatbot modes to test.",
    )
    batch_parser.add_argument(
        "--delay-ms",
        type=int,
        default=0,
        help="Delay between questions in milliseconds.",
    )
    batch_parser.add_argument(
        "--timeout-sec",
        type=int,
        default=25,
        help="HTTP timeout in seconds for each request.",
    )
    batch_parser.add_argument(
        "--no-mixed-social",
        action="store_true",
        help="Exclude the mixed-social regression prompts.",
    )
    batch_parser.add_argument("--run-id", default="", help="Optional run identifier for output files.")
    batch_parser.add_argument(
        "--topic-ids",
        nargs="+",
        default=[],
        help="Optional subset of topic IDs to test.",
    )
    batch_parser.add_argument(
        "--variant-types",
        nargs="+",
        choices=["canonical", "mixed_social"],
        default=[],
        help="Optional subset of variant types to test.",
    )
    batch_parser.add_argument(
        "--bypass-cache",
        action="store_true",
        help="Send bypassCache=true so the backend skips deterministic cache reads and writes during this batch run.",
    )
    batch_parser.add_argument(
        "--empathetic-url",
        dest="empathetic_url",
        default="",
        help="Optional empathetic target URL. Can be either the website URL or the direct API endpoint.",
    )
    batch_parser.add_argument(
        "--nonempathetic-url",
        dest="nonempathetic_url",
        default="",
        help="Optional non-empathetic target URL. Can be either the website URL or the direct API endpoint.",
    )
    batch_parser.set_defaults(func=command_api_batch)

    file_parser = subparsers.add_parser("api-file", help="Run questions from a text file against the live chatbot targets.")
    file_parser.add_argument(
        "--modes",
        nargs="+",
        choices=sorted(ENDPOINTS.keys()),
        default=["empathetic", "nonempathetic"],
        help="Chatbot modes to test.",
    )
    file_parser.add_argument(
        "--questions-file",
        default="Finance/question.txt",
        help="Path to the text file containing section headers and questions.",
    )
    file_parser.add_argument("--run-id", default="", help="Optional run identifier for output files.")
    file_parser.add_argument(
        "--output-dir",
        default="",
        help="Directory for question-file CSV/JSON outputs. Defaults to Finance/tests/output/<timestamp>/",
    )
    file_parser.add_argument(
        "--delay-ms",
        type=int,
        default=0,
        help="Delay between questions in milliseconds.",
    )
    file_parser.add_argument(
        "--timeout-sec",
        type=int,
        default=25,
        help="HTTP timeout in seconds for each request.",
    )
    file_parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="Maximum attempts per question when a timeout or empty response occurs.",
    )
    file_parser.add_argument(
        "--retry-delay-ms",
        type=int,
        default=1000,
        help="Delay between retry attempts in milliseconds.",
    )
    file_parser.add_argument(
        "--bypass-cache",
        action="store_true",
        help="Send bypassCache=true so the backend skips deterministic cache reads and writes during this run.",
    )
    file_parser.add_argument(
        "--empathetic-url",
        dest="empathetic_url",
        default=WEBSITE_TARGETS["empathetic"],
        help="Empathetic target URL. Can be the website URL or the direct API endpoint.",
    )
    file_parser.add_argument(
        "--nonempathetic-url",
        dest="nonempathetic_url",
        default=WEBSITE_TARGETS["nonempathetic"],
        help="Non-empathetic target URL. Can be the website URL or the direct API endpoint.",
    )
    file_parser.set_defaults(func=command_api_file)

    grade_parser = subparsers.add_parser(
        "grade-file",
        help="Grade an existing question-file CSV with Pass / Weak pass / Fail verdicts.",
    )
    grade_parser.add_argument(
        "--input-csv",
        default="Finance/tests/output/question_file_run/question_file_results.csv",
        help="Existing question-file CSV to grade.",
    )
    grade_parser.add_argument(
        "--questions-file",
        default="Finance/question.txt",
        help="Question source file used to generate the CSV.",
    )
    grade_parser.add_argument("--run-id", default="", help="Optional run identifier override for output metadata.")
    grade_parser.add_argument(
        "--output-dir",
        default="",
        help="Directory for graded CSV/JSON outputs. Defaults to the input CSV directory.",
    )
    grade_parser.set_defaults(func=command_grade_file)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
