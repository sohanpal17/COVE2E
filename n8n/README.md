# COVE2E n8n workflows

Importable n8n workflows that execute the **external actions** approved by the COVE2E backend
(FastAPI). The backend owns all reasoning and the Action Gate; n8n only runs deterministic
steps against the backend's Mock Insurer API and returns a structured result that the UI
animates step by step.

```
FastAPI (Action Gate) --POST webhook + X-COVE2E-Secret--> n8n workflow
                                                            |  GET/POST {backend_url}/mock-insurer/...
                                                            v
FastAPI <-- { ok, run_id, workflow, steps[], snapshot } -- Respond to Webhook
```

## Files

| File | Workflow name | Webhook path |
|------|---------------|--------------|
| `claim_submission.json` | COVE2E Claim Submission | `cove2e-claim-submission` |
| `recovery.json` | COVE2E Recovery (attach + resubmit) | `cove2e-recovery` |
| `document_workflow.json` | COVE2E Document Workflow | `cove2e-document` |
| `notification.json` | COVE2E Notification | `cove2e-notification` |
| `escalation.json` | COVE2E Escalation | `cove2e-escalation` |
| `status_polling.json` | COVE2E Status Polling & Follow-up | `cove2e-status-polling` |

## Importing

1. Open n8n (default `http://localhost:5678`).
2. Top-right menu (three dots) → **Import from file…** (or *Workflows → Add workflow → Import from file*).
3. Pick one of the six JSON files. Repeat for each file.
4. Save each workflow and toggle it **Active** so the production webhook URL is live.
   (While inactive you can still use the *Test URL* by clicking *Listen for test event*.)

Webhook URLs after activation:

```
http://localhost:5678/webhook/cove2e-claim-submission
http://localhost:5678/webhook/cove2e-recovery
http://localhost:5678/webhook/cove2e-document
http://localhost:5678/webhook/cove2e-notification
http://localhost:5678/webhook/cove2e-escalation
http://localhost:5678/webhook/cove2e-status-polling
```

Inside the docker network the backend reaches n8n as `http://n8n:5678/webhook/<path>`.

## Environment variables

### n8n side

The workflows read these with `$env.*` (docker-compose already passes them to the n8n container):

| Variable | Purpose |
|----------|---------|
| `COVE2E_WEBHOOK_SECRET` | Shared secret. Every workflow's first IF node ("Verify Secret") compares it with the `X-COVE2E-Secret` request header and answers `401 { "ok": false, "error": "invalid secret" }` on mismatch. The same value is sent back to the backend on every mock-insurer call. |
| `COVE2E_BACKEND_URL` | Fallback base URL of the backend (e.g. `http://backend:8000`) when the request body does not carry `backend_url`. Required for the scheduled polling path. |
| `COVE2E_POLL_CLAIM_ID` | Optional. External claim id (e.g. `INS-CLM-10284`) polled by the disabled Schedule Trigger in the status-polling workflow. |
| `COVE2E_NOTIFICATION_PROVIDER_URL` / `_TOKEN` | Optional. Used only if you enable the placeholder provider node in the notification workflow. |
| `COVE2E_ESCALATION_WEBHOOK_URL` | Optional. Used only if you enable the placeholder agent-notification node in the escalation workflow. |

If you run n8n outside docker-compose, export them before starting n8n, e.g.
`COVE2E_WEBHOOK_SECRET=change-me COVE2E_BACKEND_URL=http://localhost:8000 n8n start`.
Code nodes read `$env`, so `N8N_BLOCK_ENV_ACCESS_IN_NODE` must stay unset/`false`.

### Backend side

| Variable | Purpose |
|----------|---------|
| `N8N_BASE_URL` | Must point at n8n, e.g. `http://n8n:5678` (docker) or `http://localhost:5678`. The backend appends `/webhook/<path>`. |
| `N8N_WEBHOOK_SECRET` | Must equal n8n's `COVE2E_WEBHOOK_SECRET`; sent as `X-COVE2E-Secret`. |
| `DEMO_MODE` | When `true` **and** n8n is unreachable, the backend falls back to a clearly labelled demo simulation of the workflow steps instead of failing. When `false` an unreachable n8n is surfaced as an error. |

## Request / response contract

Every workflow receives a JSON POST with `X-COVE2E-Secret` and a body containing
`action_id, action_type, journey_id, claim_id, claim_number, external_claim_id, policy_number,
product_type, claim_type, claimed_amount, documents[], document_type, expected_status, message,
document_types[], backend_url, workflow`. Only the fields relevant to a workflow are used.

Every workflow responds with:

```json
{
  "ok": true,
  "run_id": "<n8n execution id>",
  "workflow": "COVE2E ...",
  "steps": [ { "key": "...", "label": "Human readable step", "status": "DONE", "detail": "..." } ],
  "snapshot": { "...last GET/POST mock-insurer response..." }
}
```

Validation failures respond `400 { "ok": false, "error": "...", "steps": [...] }`
(recovery and document workflows); a bad secret responds `401`.
Notification and escalation return `snapshot: null` plus `message` / `ticket` respectively.

## Action type → workflow → mock insurer calls

| Backend action type | Workflow (webhook path) | Mock insurer calls (in order) |
|---------------------|-------------------------|-------------------------------|
| `SUBMIT_CLAIM` | Claim Submission (`cove2e-claim-submission`) | `POST /mock-insurer/claims` → `GET /mock-insurer/claims/{external_claim_id}` |
| `ATTACH_DOCUMENT` | Recovery (`cove2e-recovery`) | `POST .../claims/{id}/documents` (per document) → `GET .../claims/{id}` |
| `RESUBMIT_CLAIM` | Recovery (`cove2e-recovery`) | `POST .../claims/{id}/resubmit` → `GET .../claims/{id}` |
| `ATTACH_AND_RESUBMIT` (any other recovery action) | Recovery (`cove2e-recovery`) | `POST .../documents` (per document) → `POST .../resubmit` → `GET .../claims/{id}` |
| `UPLOAD_DOCUMENT` / document-only flows | Document Workflow (`cove2e-document`) | `POST .../claims/{id}/documents` (per document) → `GET .../claims/{id}` |
| `NOTIFY_USER` / `REQUEST_DOCUMENTS` | Notification (`cove2e-notification`) | none (composes "Please upload: …" from `document_types`) |
| `ESCALATE` | Escalation (`cove2e-escalation`) | none (creates `ESC-<timestamp>` ticket) |
| `RAISE_FOLLOW_UP` | Status Polling & Follow-up (`cove2e-status-polling`) | `POST .../claims/{id}/query` (direction `USER`) → `GET .../claims/{id}` |
| `POLL_STATUS` / `CHECK_STATUS` | Status Polling & Follow-up (`cove2e-status-polling`) | `GET .../claims/{id}` |

The `transition` endpoint (`POST .../claims/{id}/transition`) is driven by the backend's
demo controls, not by these workflows.

## Notes

- Placeholder provider nodes (email/SMS in Notification, agent webhook in Escalation) are
  **disabled** so the workflows run end to end with no external accounts. Data passes straight
  through a disabled node.
- The Schedule Trigger in the status-polling workflow is **disabled**; see the sticky note
  inside that workflow for how to enable periodic polling.
- Nothing in these workflows calls an LLM or makes decisions beyond simple deterministic
  branching on `action_type` and document validation status.
