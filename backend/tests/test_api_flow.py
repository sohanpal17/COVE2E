"""API-level tests covering the acceptance flow end to end (no external services)."""


def _load_demo(auth_client):
    r = auth_client.post("/api/demo/load-recovery-demo")
    assert r.status_code == 200, r.text
    return r.json()


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_login_and_dashboard(auth_client):
    _load_demo(auth_client)
    r = auth_client.get("/api/dashboard")
    assert r.status_code == 200
    body = r.json()
    assert len(body["policies"]) == 2
    assert any(c["claim_number"] == "CLM-10284" for c in body["claims"])
    assert body["action_required"]
    assert "What would you like to work on?" in body["greeting"]


def test_policy_retrieval_and_qa(auth_client):
    ids = _load_demo(auth_client)
    r = auth_client.get(f"/api/policies/{ids['policy_id']}")
    assert r.status_code == 200
    p = r.json()
    assert p["sum_insured"] == 1_000_000
    assert p["waiting_period_days"] == 30
    assert p["deductible"] == 10_000
    assert any(c["kind"] == "EXCLUSION" for c in p["conditions"])

    r = auth_client.post(f"/api/policies/{ids['policy_id']}/ask", json={"question": "Is ICU covered?", "language": "en"})
    assert r.status_code == 200
    a = r.json()["answer"]
    assert a["coverage"] in {"YES", "CONDITIONAL"}
    assert "10,000" in a["answer"] or "ICU" in a["answer"]
    assert "POLICY_FACT" in a["fact_types"]

    r = auth_client.post(f"/api/policies/{ids['policy_id']}/ask", json={"question": "Is dental treatment covered?"})
    assert r.json()["answer"]["coverage"] in {"NO", "CONDITIONAL"}

    r = auth_client.post(f"/api/policies/{ids['policy_id']}/ask", json={"question": "Do I have a waiting period?"})
    assert "30 days" in r.json()["answer"]["answer"]


def test_policy_upload(auth_client):
    from pathlib import Path

    text = Path(__file__).resolve().parents[2] / "mock-data" / "policies" / "health_b.txt"
    r = auth_client.post("/api/policies/upload", files={"file": ("health_b.txt", text.read_bytes(), "text/plain")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["policy_number"] == "AHI-IND-2026-55710"
    assert body["sum_insured"] == 500_000
    assert body["knowledge_indexed"] is True
    assert body["is_demo"] is False


def test_policy_delete(auth_client):
    from pathlib import Path

    # 1. Deleting a mock policy should be forbidden
    ids = _load_demo(auth_client)
    mock_id = ids["policy_id"]
    r = auth_client.delete(f"/api/policies/{mock_id}")
    assert r.status_code == 400
    assert "Mock policies cannot be deleted" in r.json()["detail"]

    # 2. Upload a custom policy and delete it
    text = Path(__file__).resolve().parents[2] / "mock-data" / "policies" / "health_b.txt"
    r = auth_client.post("/api/policies/upload", files={"file": ("health_b.txt", text.read_bytes(), "text/plain")})
    assert r.status_code == 200
    custom_id = r.json()["id"]

    # Delete custom policy
    del_r = auth_client.delete(f"/api/policies/{custom_id}")
    assert del_r.status_code == 200, del_r.text

    # Verify policy no longer exists
    get_r = auth_client.get(f"/api/policies/{custom_id}")
    assert get_r.status_code == 404



def test_incident_claim_documents_readiness_submit(auth_client):
    ids = _load_demo(auth_client)
    r = auth_client.post("/api/incidents/analyze", json={"description": "My father was hospitalized yesterday."})
    assert r.status_code == 200
    cls = r.json()["classification"]
    assert cls["policy_type"] == "HEALTH" and cls["incident_type"] == "hospitalization"
    assert cls["matched_policy_id"] == ids["policy_id"]

    r = auth_client.post("/api/incidents/analyze", json={"description": "My car was hit while parked."})
    assert r.json()["classification"]["policy_type"] == "MOTOR"

    r = auth_client.post("/api/claims", json={"policy_id": ids["policy_id"], "claim_type": "REIMBURSEMENT", "incident_type": "hospitalization", "incident_date": "2026-09-20T10:00:00Z", "incident_description": "Hospitalised for fever", "claimed_amount": 20000})
    assert r.status_code == 201, r.text
    claim = r.json()
    required = {q["document_type"] for q in claim["requirements"] if q["required"]}
    assert {"claim_form", "policy_copy", "id_proof", "hospital_bill", "discharge_summary", "medical_certificate"} <= required

    r = auth_client.get(f"/api/claims/{claim['id']}/readiness")
    assert r.json()["percent"] < 50

    # Submission denied while documents missing
    r = auth_client.post(f"/api/claims/{claim['id']}/submit")
    assert r.status_code == 200
    assert r.json()["action"]["can_execute"] is False

    for doc in ["claim_form", "policy_copy", "id_proof", "hospital_bill", "discharge_summary", "medical_certificate"]:
        r = auth_client.post(f"/api/claims/{claim['id']}/documents/sample", data={"document_type": doc})
        assert r.status_code == 201, r.text
    body = r.json()
    assert body["readiness"]["percent"] >= 90
    assert body["readiness"]["ready_to_submit"] is True

    r = auth_client.post(f"/api/claims/{claim['id']}/submit")
    action = r.json()["action"]
    assert action["gate_decision"] == "CONFIRM" and action["can_execute"]

    r = auth_client.post(f"/api/actions/{action['id']}/approve")
    assert r.status_code == 200, r.text
    r = auth_client.post(f"/api/actions/{action['id']}/execute", json={"language": "en"})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["verification"]["outcome"] == "VERIFIED"
    assert res["verification"]["after_state"] == "UNDER_REVIEW"

    r = auth_client.get(f"/api/claims/{claim['id']}/tracking")
    tr = r.json()
    assert tr["current_state"] == "UNDER_REVIEW"
    assert tr["user_action_required"] is False


def test_primary_recovery_demo_via_api(auth_client):
    ids = _load_demo(auth_client)
    jid = ids["journey_id"]

    # "Why is my claim stuck?" through Ask COVE2E
    r = auth_client.post("/api/chat", json={"message": "My claim has been stuck for eight days.", "language": "en"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["intent"] == "STUCK_CLAIM"
    assert body["data"]["investigation"]["blocker"] == "missing_requested_document"
    assert "approved" not in body["reply"].lower()

    r = auth_client.get(f"/api/journeys/{jid}/investigation")
    inv = r.json()
    assert inv["current_state"] == "QUERY_RAISED"
    assert inv["external_status"] == "DOCUMENT_PENDING"
    assert len(inv["checks"]) >= 6

    # Upload the missing certificate (demo sample)
    r = auth_client.post(f"/api/claims/{ids['claim_id']}/documents/sample", data={"document_type": "medical_certificate"})
    assert r.status_code == 201

    r = auth_client.get(f"/api/journeys/{jid}/recovery")
    plan = r.json()
    assert plan["blocker"] == "requested_document_not_attached"
    assert plan["action"]["gate_decision"] == "CONFIRM"
    assert plan["action"]["can_execute"] is True
    assert [s["label"] for s in plan["steps"]][:2] == ["Obtain medical certificate", "Validate document"]

    aid = plan["action"]["id"]
    # Executing without approval is rejected
    r = auth_client.post(f"/api/actions/{aid}/execute")
    assert r.status_code == 409
    r = auth_client.post(f"/api/actions/{aid}/approve")
    assert r.status_code == 200
    r = auth_client.post(f"/api/actions/{aid}/execute")
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["verification"]["before_state"] == "DOCUMENT_PENDING"
    assert res["verification"]["after_state"] == "UNDER_REVIEW"
    assert res["recovery_status"] == "SUCCEEDED"
    assert "medical certificate" in res["final_message"].lower()

    r = auth_client.get(f"/api/journeys/{jid}")
    assert r.json()["current_state"] == "UNDER_REVIEW"

    r = auth_client.get("/api/audit?limit=200")
    actions = {a["action"] for a in r.json()}
    assert {"USER_REQUESTED_RECOVERY", "AI_IDENTIFIED_BLOCKER", "ACTION_PROPOSED", "ACTION_GATE_APPROVED", "USER_CONFIRMED", "EXTERNAL_STATE_CHECKED", "RECOVERY_VERIFIED", "JOURNEY_UPDATED"} <= actions


def test_conflicting_state_escalation_via_api(auth_client):
    ids = _load_demo(auth_client)
    scen = ids["scenarios"]["CONFLICTING_STATE"]
    r = auth_client.get(f"/api/journeys/{scen['journey_id']}/recovery")
    plan = r.json()
    assert plan["risk_class"] == "HUMAN_ESCALATION_REQUIRED"
    assert plan["escalation_id"]
    r = auth_client.get(f"/api/escalations/{plan['escalation_id']}")
    packet = r.json()
    assert packet["problem"] and packet["evidence"] and packet["recommended_action"]
    r = auth_client.get(f"/api/journeys/{scen['journey_id']}")
    assert r.json()["current_state"] == "ESCALATED"


def test_document_inconsistency_confirm_value(auth_client):
    ids = _load_demo(auth_client)
    scen = ids["scenarios"]["DOCUMENT_INCONSISTENCY"]
    r = auth_client.get(f"/api/journeys/{scen['journey_id']}/recovery")
    plan = r.json()
    assert plan["blocker"] == "document_inconsistency"
    assert plan["action"]["action_type"] == "CONFIRM_DOCUMENT_VALUE"
    r = auth_client.post(f"/api/claims/{scen['claim_id']}/confirm-value", json={"field": "admission_date", "value": "2026-09-10", "note": "Bill date is correct"})
    assert r.status_code == 200, r.text
    r = auth_client.get(f"/api/claims/{scen['claim_id']}/readiness")
    assert not any("mismatch" in i["label"].lower() for i in r.json()["items"])
    r = auth_client.get(f"/api/journeys/{scen['journey_id']}/investigation")
    assert r.json()["blocker"] == "ready_to_submit"


def test_discovery_never_says_best(auth_client):
    r = auth_client.post("/api/discovery", json={"age": 34, "family_situation": "married with children", "budget_annual": 20000, "risk_requirements": ["icu"], "insurance_type": "HEALTH"})
    assert r.status_code == 200
    body = r.json()
    assert body["matches"][0]["product"]["name"] == "Suraksha Family Health Plus"
    assert "best" not in body["narrative"].lower()
    assert "matches the requirements you provided" in body["narrative"]


def test_user_isolation(auth_client, client):
    ids = _load_demo(auth_client)
    other = client.post("/api/auth/demo-login", json={"demo_code": "demo-hi"}).json()["access_token"]
    r = client.get(f"/api/claims/{ids['claim_id']}", headers={"Authorization": f"Bearer {other}"})
    assert r.status_code == 404


def test_voice_requires_sarvam_key(auth_client):
    r = auth_client.post("/api/voice/transcribe", files={"file": ("a.webm", b"xxx", "audio/webm")})
    assert r.status_code == 503


def test_translate_fallback(auth_client):
    r = auth_client.post("/api/translate", json={"text": "Hello", "source_language": "en", "target_language": "hi"})
    assert r.status_code == 200
    assert r.json()["source"] in {"sarvam", "fallback-untranslated"}
