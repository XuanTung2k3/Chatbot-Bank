# Chatbot QA Process

Use this process after deploying the four updated backends and frontend sites.

## 0. Deploy And Runtime Tuning

Deploy each backend as usual, then apply Cloud Run runtime settings to reduce cold-start impact and keep concurrent users stable:

```bash
gcloud run services update m-finance --region us-central1 --min-instances=1 --concurrency=20 --timeout=60s
gcloud run services update non-m-finance --region us-central1 --min-instances=1 --concurrency=20 --timeout=60s
gcloud run services update emp-spa --region us-central1 --min-instances=1 --concurrency=20 --timeout=60s
gcloud run services update non-emp-spa --region us-central1 --min-instances=1 --concurrency=20 --timeout=60s
```

Deploy each Firebase Hosting site after the frontend changes:

```bash
cd /Users/xntung/Downloads/with_avatar/Finance/Empathetic && firebase deploy --only hosting
cd /Users/xntung/Downloads/with_avatar/Finance/NonEmpathetic && firebase deploy --only hosting
cd /Users/xntung/Downloads/with_avatar/Spa/Empathetic && firebase deploy --only hosting
cd /Users/xntung/Downloads/with_avatar/Spa/Non-empathetic && firebase deploy --only hosting
```

## 1. API Smoke Test

Run the shared deployed-endpoint matrix first:

```bash
cd /Users/xntung/Downloads/with_avatar
python3 chatbot_qa_smoke_test.py
```

The script checks the four endpoints used by the standalone websites:

- `finance_emp`: Empathetic AmazingBank
- `finance_non`: Non-empathetic AmazingBank
- `spa_emp`: Empathetic WELLBEING SPA
- `spa_non`: Non-empathetic WELLBEING SPA

Fix any `FAIL` result before manual website testing.

## 2. Automated Hard API Test

Run the safe hard-test matrix after the smoke test passes:

```bash
cd /Users/xntung/Downloads/with_avatar
python3 chatbot_hard_test.py --mode safe-hard
```

The hard test asks service, follow-up, exact-fact, typo-heavy, brand-leak, prompt-injection, repetition, greeting, and closer questions. It writes timestamped reports under `qa_results/`:

- `hard_test_<timestamp>.json`: full raw responses, metadata, latency, and failure codes.
- `hard_test_<timestamp>.md`: readable summary grouped by endpoint and failure type.

Failure-code interpretation:

- `BAD_FALLBACK`: fix frontend fallback strings or backend empty-response policy.
- `NEXT_STEP_NONACTIONABLE`: fix acknowledgement handling or `is_actionable_service_question`.
- `BRAND_LEAK`: add sanitizer patterns, tighten RAG prompt rules, and bump cache version.
- `EMPATHY_TOO_WEAK`: update empathetic opener, bridge, icon policy, or prompt examples.
- `NON_EM_TOO_SOFT`: update non-em tone stripping and prompt examples.
- `FACT_MISMATCH`: align paired factual catalogs and expected product/service core.
- `DUPLICATE_TEXT`: fix post-processing order or repeated suffix insertion.
- `EXACT_FACT_GUESSED`: tighten strict grounding detection or safe fallback handling.
- `LATENCY_HIGH`: inspect RAG timeout/cache behavior and Cloud Run min instances/concurrency.

## 3. Browser UI Probe

Run the website-level probe after API hard-test issues are understood:

```bash
cd /Users/xntung/Downloads/with_avatar
npm install --no-save @playwright/test@latest
npx -y playwright@latest install chromium
npx -y @playwright/test@latest test website_ui_probe.spec.mjs --project=chromium
```

The local install is needed because this repo does not have a Node package manifest for Playwright. The probe opens each deployed website in a fresh browser context, checks that chat auto-opens, verifies the welcome text, sends `Hello`, one service question, and `Ok thanks`, and saves screenshots to `qa_results/ui/` only on failure.

## 4. Manual Website A/B Test

Open each site in a clean browser profile or incognito window. Clear local storage before each run.

Use the same question sequence for each pair:

- Bank pair: `Tell me about card service`, `I want you talk about loan service`, `What savings options do you have?`, `What is the annual fee?`, `Which is best for me?`, `Techcombank credit card phone number`, `Ok thanks`.
- Spa pair: `What spa services do you offer?`, `Tell me about massage services`, `I want skin care`, `What are your opening hours?`, `JW Marriott spa phone number`, `L'Occitane treatment details`, `Ok thanks`.

Record these fields for each answer:

- Response text
- Visible tone: empathetic or direct
- Any repeated phrase or vague filler
- Any real brand/contact leakage
- Whether `Next step:` appears only when useful
- Approximate latency: fast, acceptable, slow
- API metadata if visible: `rag_used`, `response_mode`, `cache_hit`

## 5. Pass Criteria

- No page shows `I could not process that request yet`.
- `Ok thanks` gives a short closing response and no `Next step:`.
- Empathetic answers are warmer but not less informative.
- Non-empathetic answers are direct, neutral, and emoji-free.
- Bank and Spa paired modes share the same factual core for the same intent.
- No answer exposes source brands, real phone numbers, or real emails.
