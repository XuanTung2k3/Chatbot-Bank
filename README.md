# Chatbot-Bank

Tutorial-ready codebase for a banking chatbot case study built with two modes:

- `Empathetic`
- `Non-Empathetic`

This repository is intentionally trimmed down to the files needed to:

- read how the system is built,
- inspect the active Finance chatbot code,
- follow the deployment tutorial,
- and review the Finance QA evidence after deployment.

## Start Here

- Main case study: [docs/bank-chatbot-case-study.md](docs/bank-chatbot-case-study.md)
- Deployment and QA process: [CHATBOT_QA_PROCESS.md](CHATBOT_QA_PROCESS.md)
- Runtime tuning notes: [chatbot_runtime_tuning.md](chatbot_runtime_tuning.md)

## Repository Scope

Included:

- Active Finance chatbot pair only:
  - `Finance/Empathetic`
  - `Finance/NonEmpathetic`
- Finance deployment and evaluation scripts
- Finance post-deploy output artifacts used in the tutorial
- Documentation assets for the case study

Excluded:

- Other chatbot experiments and domains
- Old patch bundles and zip archives
- Local caches, generated folders, and unrelated workspace files

## Main Folders

- `docs/`
  Case study documentation and tutorial figures.

- `Finance/Empathetic/`
  Empathetic Finance chatbot frontend and backend.

- `Finance/NonEmpathetic/`
  Non-Empathetic Finance chatbot frontend and backend.

- `Finance/tests/`
  Finance corpus, verification tools, and post-deploy evidence.

## Deployable Parts

- Cloud Run backends:
  - `Finance/Empathetic/Backend`
  - `Finance/NonEmpathetic/Backend`

- Firebase Hosting frontends:
  - `Finance/Empathetic`
  - `Finance/NonEmpathetic`

The full deployment walkthrough is in [docs/bank-chatbot-case-study.md](docs/bank-chatbot-case-study.md).

## Verification

Useful commands after deployment:

```bash
python3 chatbot_qa_smoke_test.py
python3 chatbot_hard_test.py --mode safe-hard
python3 Finance/tests/smoke_test_live_endpoints.py
python3 -m unittest Finance.tests.test_chatbot_test_flow_assets
python3 -m unittest Finance.tests.test_chatbot_turns
```
