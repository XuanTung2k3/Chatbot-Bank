import json
import sys
import urllib.error
import urllib.request
import uuid


ENDPOINTS = {
    "empathetic": "https://m-finance-137003227004.us-central1.run.app",
    "nonempathetic": "https://non-m-finance-137003227004.us-central1.run.app",
}

GREETING_FALLBACK_MARKERS = (
    "provide an amazingbank service or question to continue",
    "whenever you are ready",
)


def post_json(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def assert_true(condition: bool, message: str):
    if not condition:
        raise AssertionError(message)


def smoke_endpoint(name: str, url: str):
    user_hash = str(uuid.uuid4())
    init_payload = {"userHash": user_hash, "question": "", "initConversation": True}
    init_response = post_json(url, init_payload)
    print(f"[{name}] init -> {init_response.get('response_mode')} / {init_response.get('grounding_scope')}")

    screenshot_question = "Hi i need to open up an account. Need some info on what docs i need to have on me?"
    screenshot_response = post_json(url, {"userHash": user_hash, "question": screenshot_question})
    print(f"[{name}] screenshot -> {screenshot_response.get('turn_classification')} / {screenshot_response.get('grounding_scope')}")
    response_text = (screenshot_response.get("response") or "").lower()
    assert_true(screenshot_response.get("turn_classification") == "substantive", f"{name}: screenshot turn misclassified")
    assert_true(not any(marker in response_text for marker in GREETING_FALLBACK_MARKERS), f"{name}: screenshot response fell back to greeting text")

    greeting_response = post_json(url, {"userHash": user_hash, "question": "Hello"})
    print(f"[{name}] greeting -> {greeting_response.get('turn_classification')} / {greeting_response.get('grounding_scope')}")
    assert_true(greeting_response.get("turn_classification") == "greeting_only", f"{name}: greeting classification mismatch")

    fee_response = post_json(url, {"userHash": user_hash, "question": "Thanks, what is the annual fee?"})
    print(f"[{name}] fee -> {fee_response.get('turn_classification')} / {fee_response.get('grounding_scope')}")
    assert_true(fee_response.get("turn_classification") == "substantive", f"{name}: fee turn misclassified")
    assert_true(fee_response.get("grounding_scope") in {"live_fallback", "official_rag"}, f"{name}: fee grounding scope mismatch")

    rate_response = post_json(url, {"userHash": user_hash, "question": "What is the current savings rate today?"})
    print(f"[{name}] rate -> {rate_response.get('turn_classification')} / {rate_response.get('grounding_scope')}")
    assert_true(rate_response.get("turn_classification") == "substantive", f"{name}: rate turn misclassified")
    assert_true(rate_response.get("grounding_scope") in {"live_fallback", "official_rag"}, f"{name}: rate grounding scope mismatch")


def main():
    failures = []
    for name, url in ENDPOINTS.items():
        try:
            smoke_endpoint(name, url)
        except (AssertionError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            failures.append(f"{name}: {exc}")

    if failures:
        print("\n".join(failures), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
