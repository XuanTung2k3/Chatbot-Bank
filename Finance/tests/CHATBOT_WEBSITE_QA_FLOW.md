# English-Only Website QA Flow

This guide is the manual website half of the hybrid test plan. Use it together with `chatbot_test_flow.py` so the website run and the API run stay aligned.

## Entry Points

Empathetic mode:
- `Finance/Empathetic/Frontend/index.html`
- `Finance/Empathetic/empathetic-standalone.html`

Non-Empathetic mode:
- `Finance/NonEmpathetic/Frontend/index.html`
- `Finance/NonEmpathetic/non-empathetic-standalone.html`

Live backends used by the frontends:
- `https://m-finance-137003227004.us-central1.run.app`
- `https://non-m-finance-137003227004.us-central1.run.app`

Hosted website targets:
- `https://vincent-bank-empathetic.web.app/`
- `https://vincent-bank-non-empathetic.web.app/`

## Preparation

1. Generate the evaluation sheet:

```bash
uv run python Finance/tests/chatbot_test_flow.py prepare-sheet
```

2. Open the generated CSV at `Finance/tests/output/chatbot_evaluation_sheet_template.csv`.
3. Filter to `channel=website` for the manual browser pass.
4. Keep the API rows for the later comparison pass.

## Session Rules

- Use English input only.
- Do not use Vietnamese prompts.
- One topic bucket per website session.
- The frontend stops after `15` bot responses, so do not combine multiple topic buckets into one session.
- Use the built-in refresh/reset control or reload the page before each new topic bucket so a new session starts.
- Run the `mixed_social_regression` bucket as a separate session after the 10 canonical topic sessions.

## Manual Website Pass

For each mode (`empathetic`, then `nonempathetic`):

1. Open the correct website.
2. Start a fresh session.
3. Ask the 10 questions from one topic bucket in order.
4. Record in the CSV:
   - `session_id` if visible in the UI or final message
   - the visible `response`
   - `verdict`
   - `error_type`
   - `suspected_layer`
   - `notes`
5. Also record UX evidence in `notes` when present:
   - loader hangs
   - visible server error
   - response cut off
   - timeout filler
   - session ending too early
   - response text that clearly differs from the API response for the same question
6. After the 10th question, reset the chat and move to the next topic bucket.
7. After all 10 topic buckets, run the `mixed_social_regression` session.

## API Comparison Pass

Run the API batch after the website pass:

```bash
uv run python Finance/tests/chatbot_test_flow.py api-batch
```

Outputs are written to `Finance/tests/output/<timestamp>/`:
- `api_batch_results.csv`
- `api_batch_results.json`
- `api_batch_summary.json`

## Question File Run

If you want to run all questions from `Finance/question.txt` and save every chatbot answer for both bank modes:

```bash
uv run python Finance/tests/chatbot_test_flow.py api-file \
  --questions-file Finance/question.txt \
  --empathetic-url https://vincent-bank-empathetic.web.app/ \
  --nonempathetic-url https://vincent-bank-non-empathetic.web.app/
```

Outputs are written to `Finance/tests/output/<timestamp>/`:
- `question_file_results.csv`
- `question_file_results.json`
- `question_file_summary.json`

Notes:
- `--empathetic-url` and `--nonempathetic-url` can be either website URLs or direct API endpoints.
- The runner resolves website URLs to the underlying chatbot API automatically.
- Add `--bypass-cache` if you want the backend to skip deterministic cache reuse during the run.

Compare each website answer to the API answer for the same `mode` and `question_id`.

Interpretation:
- Website fails, API passes: likely frontend session or UI handling.
- Website fails, API fails: likely backend routing, playbook, retrieval, prompt, or post-processing.
- API metadata shows `turn_classification != substantive`: routing or social-turn classifier.
- API metadata shows `grounding_scope = model_only` for a bank-specific question: retrieval gating or missing official-source grounding.
- API metadata shows `grounding_scope = public_guidance` for a bank-specific product question: retrieval-scope policy issue.

## Pass Criteria

Mark `Pass` only when all are true:
- Answer is in English.
- Answer uses AmazingBank branding only.
- Answer is relevant to the exact question.
- Answer does not fall back to generic prompt text such as "ask a question to continue".
- Exact facts are grounded or explicitly marked as not fully verified.

Mark `Weak pass` when the answer is relevant but too generic, incompletely grounded, or stylistically off.

Mark `Fail` when the answer is off-topic, unsupported, in the wrong language, leaks the hidden source-bank brand, or ignores the actual question.

## Validation Commands

Use `uv` for the local validation steps as well:

```bash
uv run python -m unittest discover -s Finance/tests -p 'test_*.py'
uv run python -m py_compile Finance/tests/chatbot_test_flow.py Finance/tests/test_chatbot_test_flow_assets.py
```
