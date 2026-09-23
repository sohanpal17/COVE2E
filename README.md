# COVE2E — Coverage End-to-End

> **When your insurance journey gets stuck, COVE2E finds out why and helps get it moving again.**

Hackathon MVP for the **Paytm Build for AI Hackathon** · Track: **AI-Powered Financial Journeys**.

COVE2E is not an insurance chatbot. The conversation is only the interface; the product is an
**Insurance Journey Intelligence and Recovery System** that maintains awareness of the user's policies,
policy terms, uploaded documents, claim state, insurer queries, journey state, previous actions and
recovery attempts — and runs a controlled loop:

```
UNDERSTAND → INVESTIGATE → REASON → POLICY / ACTION GATE → EXECUTE → VERIFY → UPDATE JOURNEY → RESOLVE / ESCALATE
```

---

## 1. Product overview

| Area | What it does |
|---|---|
| Insurance Discovery | Needs analysis + side-by-side comparison. Explains *why an option matches the requirements you provided*; never says "best". |
| Policy Intelligence | Upload a policy PDF/text → deterministic extraction → structured profile in PostgreSQL → knowledge layer (Cognee or local fallback). |
| Policy Companion | Policy-specific Q&A ("Is ICU covered?") grounded in retrieved policy context; answers labelled Policy Fact / AI Interpretation / Missing Information / General Guidance / External Insurer Decision. |
| Incident Understanding | "My father was hospitalized yesterday" → incident type, relevant policy, urgency, required information, next actions. |
| Claim Agent | Incident capture → coverage understanding → claim type → dynamic document checklist. |
| Document Intelligence | Classification, key-value/date extraction, validation, cross-document inconsistency detection (never concludes a claim is invalid). |
| Claim Readiness | Documentation/process completeness %, outstanding issues, next action. Explicitly *not* an approval prediction. |
| Journey State Engine | Deterministic state machine with audited transitions. |
| Journey Investigation | Checks policy, claim state, documents, insurer query, timeline, previous actions and external insurer state → root-cause blocker with evidence and confidence. |
| Journey Recovery | Blocker → recovery plan → action classified AUTO_RECOVERABLE / USER_CONFIRMATION_REQUIRED / HUMAN_ESCALATION_REQUIRED. |
| Action Gate | Decides SAFE / CONFIRM / ESCALATE / DENY for every proposed action. Mandatory gate between AI and execution. |
| Workflow Executor | Approved actions run through **n8n** webhooks against the mock insurer. |
| Outcome Verifier | Re-queries the insurer after every external action; only a verified state change updates the journey. |
| Human Escalation | Escalation packet (problem, evidence, state, actions attempted, reason, recommended human action). |
| Multilingual + voice | English / Hindi / Marathi via **Sarvam AI**; microphone → Sarvam speech-to-text; optional text-to-speech. |

## 2. Architecture

```
                          React + Vite + Tailwind (frontend/)
                                        │  REST (JWT)
                                        ▼
                     FastAPI (backend/app) — the security & decision boundary
   ┌───────────────┬───────────────┬───────────────┬────────────────┬──────────────────┐
   │ agents/       │ engines/      │ services/     │ integrations/  │ api/routers/     │
   │ orchestrator  │ journey_state │ policy, claim │ sarvam_client  │ auth, dashboard  │
   │ policy_agent  │ investigation │ readiness     │ n8n_client     │ policies, claims │
   │ claim_agent   │ recovery      │ document_int. │ document_extr. │ journeys, actions│
   │ journey_agent │ action_gate   │ workflow_exec │ (cognee via    │ voice, translate │
   │ investigation │ outcome_verif │ mock_insurer  │  services/     │ escalations, demo│
   │ recovery      │               │ escalation    │  policy_knowl.)│ mock_insurer     │
   └───────────────┴───────────────┴───────────────┴────────────────┴──────────────────┘
          │ Sarvam (proposes)        │ n8n webhooks (executes)          │ PostgreSQL
          ▼                          ▼                                  ▼
   sarvam-105b / saaras:v3     n8n workflows → Mock Insurer API → Outcome Verifier → Journey state
```

**Safety architecture.** The LLM proposes structured output (Pydantic-validated). FastAPI validates it
deterministically. The Investigation/Recovery engines derive the blocker and plan from database + insurer
state, not from model text. The Action Gate decides. n8n executes. The Outcome Verifier confirms by
re-reading the insurer before the journey is updated. Every important step writes an `audit_logs` row.

## 3. Technology stack

* **Frontend:** React 18, Vite, TypeScript, Tailwind CSS, React Router, TanStack Query, Axios, Lucide, Recharts
* **Backend:** Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, httpx, PyJWT, pypdf
* **Database:** PostgreSQL (primary). SQLite fallback for quick local runs/tests.
* **AI:** Sarvam AI (`/v1/chat/completions` with `sarvam-105b`, `/speech-to-text` with `saaras:v3`, `/translate`, `/text-to-speech`)
* **Knowledge:** Cognee (optional, `requirements-cognee.txt`) with `LocalPolicyKnowledgeService` fallback
* **Workflows:** n8n (six importable workflows in `n8n/`)

## 4. Prerequisites

* Python 3.11+, Node 20+, PostgreSQL 14+ (or use SQLite), optionally Docker + n8n.

## 5. Environment variables

Copy `backend/.env.example` → `backend/.env`:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg2://cove2e:cove2e@localhost:5432/cove2e` (or `sqlite:///./cove2e.db`) |
| `SARVAM_API_KEY` | Sarvam subscription key. Empty → deterministic fallbacks (demo still works). |
| `SARVAM_CHAT_MODEL` / `SARVAM_STT_MODEL` | default `sarvam-105b` / `saaras:v3` |
| `COGNEE_API_KEY`, `COGNEE_ENABLED` | Enable the Cognee knowledge layer. |
| `N8N_BASE_URL`, `N8N_WEBHOOK_SECRET` | Where to trigger workflows and the shared secret. |
| `BACKEND_PUBLIC_URL` | URL n8n uses to call the mock insurer back. |
| `JWT_SECRET`, `JWT_EXPIRE_MINUTES` | Demo auth. |
| `DEMO_MODE`, `APP_ENV`, `CORS_ORIGINS`, `UPLOAD_DIR`, `MAX_UPLOAD_MB` | App behaviour. |

No Claude/Anthropic keys are used anywhere.

## 6. Local setup (fastest path)

```bash
# Backend
cd backend
python -m venv .venv && . .venv/Scripts/activate   # Windows; use .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
copy .env.example .env                              # edit DATABASE_URL etc.
alembic upgrade head                                # creates the schema (optional with SQLite: tables auto-create in non-production)
uvicorn app.main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install
npm run dev                                         # http://localhost:5173 (proxies /api → :8000)
```

Open http://localhost:5173 → **Demo login** → tick **Load Recovery Demo** → Dashboard.

## 7. PostgreSQL setup

```sql
CREATE ROLE cove2e WITH LOGIN PASSWORD 'cove2e';
CREATE DATABASE cove2e OWNER cove2e;
```
Set `DATABASE_URL=postgresql+psycopg2://cove2e:cove2e@localhost:5432/cove2e`, then `alembic upgrade head`.
Indexes exist on `user_id`, `policy_id`, `claim_id`, `journey_id`, `state`/`status` and `created_at`.

## 8. Backend setup details

* Entrypoint `backend/app/main.py`; OpenAPI docs at http://localhost:8000/docs.
* Migrations: `alembic revision --autogenerate -m "..."` then `alembic upgrade head`.
* Tests: `cd backend && python -m pytest` (25 tests, SQLite temp DB, n8n unreachable → demo fallback path).

## 9. Frontend setup details

* `frontend/.env.example` → `VITE_API_BASE_URL` (leave empty to use the Vite proxy).
* `npm run build` produces `dist/` served by nginx in Docker.

## 10. n8n setup

1. `docker compose up n8n` (or run n8n locally) → http://localhost:5678.
2. Import the six workflows from `n8n/*.json` (Import from file) and activate them.
3. In n8n set env `COVE2E_WEBHOOK_SECRET` (= backend `N8N_WEBHOOK_SECRET`) and `COVE2E_BACKEND_URL`.
4. Backend `.env`: `N8N_BASE_URL=http://localhost:5678`, `BACKEND_PUBLIC_URL=http://host.docker.internal:8000` when n8n runs in Docker and the backend on the host.

Action → workflow mapping: SUBMIT_CLAIM → `claim_submission`; ATTACH_AND_RESUBMIT / RESUBMIT_CLAIM → `recovery`;
ATTACH_DOCUMENT → `document_workflow`; POLL_STATUS / RAISE_FOLLOW_UP → `status_polling`;
REQUEST_DOCUMENT_FROM_USER / NOTIFY_USER → `notification`; ESCALATE → `escalation`.

If n8n is unreachable **and** `DEMO_MODE=true`, the executor runs the identical steps in-process against the
mock insurer and labels the result `demo-fallback` in the API and UI. In production mode the failure is returned, never hidden.

## 11. Cognee setup

```bash
pip install -r backend/requirements-cognee.txt
# backend/.env
COGNEE_ENABLED=true
COGNEE_API_KEY=<your LLM key for cognee>   # exported to LLM_API_KEY for the cognee SDK
```
Each policy is ingested into its own dataset (`cove2e_policy_<id>`) and searched with graph completion;
results are merged with the structured PostgreSQL rows. Without Cognee, `LocalPolicyKnowledgeService`
(section/keyword retrieval over the extracted text + coverage/condition rows) answers with the same interface.

## 12. Sarvam setup

Set `SARVAM_API_KEY`. Used for: intent detection, policy answers, incident classification, investigation/recovery
explanations, discovery narrative, translation (hi/mr), speech-to-text (microphone button), text-to-speech.
All structured calls validate against Pydantic schemas; deterministic decisions are never overridden by the model.
Without a key every feature still works with deterministic English text (Hindi/Marathi UI labels remain translated).

## 13. Demo data

`POST /api/demo/load-recovery-demo` (button **Load Recovery Demo** on Login/Dashboard) resets the demo user and creates:

| Claim | Scenario | State |
|---|---|---|
| **CLM-10284** | Stuck claim (primary demo) | Insurer `DOCUMENT_PENDING`, query "Please provide the medical certificate…" raised 3 days ago, journey `QUERY_RAISED` |
| CLM-10301 | Normal motor claim | `UNDER_REVIEW`, all documents |
| CLM-10322 | Missing documents | `DRAFT`, 4 required documents missing |
| CLM-10345 | Document inconsistency | Admission date 10 Sep (bill) vs 12 Sep (discharge summary) |
| CLM-10367 | Conflicting external state | `APPROVED` / settlement `PENDING` / payment `COMPLETED` |

Products: Health Insurance A/B, Motor Insurance A/B (`mock-data/policies/*.txt`). Sample documents in `mock-data/documents/`.

## 14. Running the stuck-claim recovery demo

1. Login (`demo`) with **Load Recovery Demo** ticked.
2. Dashboard → *Ask COVE2E*: type **"My claim has been stuck for eight days."** (or use the mic).
3. COVE2E investigates (✓ Policy ✓ Claim state ✓ Documents ✓ Insurer query ✓ Timeline ✓ Previous actions) and shows the root cause: *medical certificate requested but not submitted*. Click **Open investigation**.
4. Click **Prepare recovery** → Recovery plan (Obtain → Validate → Attach → Resubmit → Verify). The Action Gate says **CONFIRM**; the prerequisite "Medical certificate uploaded" is unmet → click **Use sample medical certificate (demo)** (or upload your own).
5. Click **Confirm Recovery** → n8n executes (or labelled demo fallback) → progress ✓ Preparing ✓ Validating ✓ Attaching ✓ Resubmitting.
6. **Verifying external state…** `DOCUMENT_PENDING → UNDER_REVIEW` → **RECOVERY SUCCESSFUL ✓**.
7. Final response: *"Your claim was waiting for the medical certificate. The document has been submitted and the claim is now under review."*
8. Secondary scenarios: Claims → CLM-10345 (**Investigate** → inconsistency → confirm correct value; nothing is auto-changed) and CLM-10367 (**Investigate** → conflicting state → **escalation packet**, journey `ESCALATED`).

## 15. API documentation

Swagger UI: http://localhost:8000/docs · ReDoc: http://localhost:8000/redoc

Key endpoints: `POST /api/auth/demo-login`, `GET /api/dashboard`, `GET/POST /api/policies[/upload|/{id}|/{id}/ask]`,
`POST /api/incidents/analyze`, `POST /api/claims`, `GET /api/claims/{id}[/readiness|/timeline|/tracking]`,
`POST /api/claims/{id}/documents[/sample]`, `POST /api/claims/{id}/submit`, `POST /api/claims/{id}/investigate`,
`POST /api/claims/{id}/recovery-plan`, `POST /api/claims/{id}/confirm-value`, `POST /api/actions/{id}/approve`,
`POST /api/actions/{id}/execute`, `GET /api/journeys/{id}[/investigation|/recovery|/recovery-attempts]`,
`POST /api/chat`, `POST /api/voice/transcribe`, `POST /api/translate`, `POST /api/escalations`, `GET /api/audit`,
`POST /api/demo/load-recovery-demo`, mock insurer under `/mock-insurer/claims…`.

## 16. AI architecture

```
                 Sarvam (sarvam-105b)
                        │ structured JSON (Pydantic-validated)
   ┌────────────────────┼────────────────────┐
   Policy Agent     Claim Agent        Journey Agent
   (policy Q&A)    (incident class.)  (tracking explain)
                        │
              Investigation Engine (deterministic)
                        │
                Recovery Engine (deterministic)
                        │
                    Action Gate
                        │
                       n8n → Mock Insurer
                        │
                 Outcome Verifier → Journey State
```
Specialised prompts live in `backend/app/agents/*`; there is no single giant prompt. Schemas: `backend/app/schemas/ai.py`.

## 17. Safety architecture

* AI never touches DB/claim/financial/insurer state; it returns structured proposals only.
* Deterministic engines decide blockers, plans and gate outcomes; LLM text is explanation, not evidence.
* Every external action needs Gate approval and user confirmation when it modifies the insurer claim.
* Outcome verification after every external action; unchanged → reinvestigate; repeated failure or conflict → escalate.
* Readiness % is completeness, never approval probability. Product language avoids guarantees.
* Backend is the security boundary: JWT auth, per-user data isolation, file type/size validation, CORS, audit log, no keys in the frontend.

## 18. Sponsor integrations

* **Sarvam AI** — conversation, reasoning, multilingual (hi/mr), STT, TTS.
* **Cognee** — policy knowledge graph (with mandatory local fallback).
* **n8n** — claim submission, recovery, document, notification, escalation, status polling workflows.

## 19. Known limitations

* OCR for scanned images is not bundled (text PDFs and .txt are extracted; images are flagged for review).
* The Postgres role/password must be provisioned by you; the app runs on SQLite otherwise.
* Sarvam/Cognee/n8n are exercised through adapters with fallbacks; live behaviour depends on your keys and services.
* Cognee cloud API specifics may differ by version; the adapter targets the Python SDK (`cognee.add/cognify/search`).
* TTS is optional and only active with a Sarvam key.
