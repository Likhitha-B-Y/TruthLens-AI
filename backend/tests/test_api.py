import io
import time

from conftest import SAMPLES

ANSWER = ("The Eiffel Tower was completed in 1889 and is located in Paris. It is 150 metres tall. "
          "The tower's top-floor restaurant has held three Michelin stars since 2015.")


def upload(client, name, content=None, ctype="text/plain"):
    data = content if content is not None else (SAMPLES / name).read_bytes()
    return client.post("/api/documents", files=[("files", (name, io.BytesIO(data), ctype))])


# ---------------------------------------------------------------------------- system
def test_health_and_model_status(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["models_ready"] is True
    m = client.get("/api/models/status").json()
    assert m["nli"]["state"] == "ready" and m["embedding"]["state"] in ("ready", "fallback")
    assert "choices" in m


def test_openapi_docs_available(client):
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200


# -------------------------------------------------------------------------- library
def test_upload_list_search_filter_delete(client):
    r = upload(client, "eiffel_tower_factsheet.txt")
    assert r.status_code == 201 and r.json()["uploaded"] == 1
    doc = r.json()["results"][0]["document"]
    assert doc["page_count"] == 1 and doc["passage_count"] >= 1 and "stored_path" not in doc
    upload(client, "solar_system_notes.pdf", ctype="application/pdf")
    upload(client, "photosynthesis_overview.docx")
    assert client.get("/api/documents").json()["total"] == 3
    assert client.get("/api/documents?q=solar").json()["total"] == 1
    assert client.get("/api/documents?ext=pdf").json()["documents"][0]["name"] == "solar_system_notes.pdf"
    assert client.get("/api/documents?q=nothing-here").json()["total"] == 0
    detail = client.get(f"/api/documents/{doc['id']}").json()
    assert detail["passages"]
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 200
    assert client.get("/api/documents").json()["total"] == 2
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 404


def test_duplicate_upload_is_detected(client):
    upload(client, "eiffel_tower_factsheet.txt")
    r = upload(client, "eiffel_tower_factsheet.txt").json()
    assert r["uploaded"] == 0 and r["results"][0]["duplicate"] is True
    assert client.get("/api/documents").json()["total"] == 1


def test_bad_uploads_report_errors_per_file(client):
    files = [("files", ("a.xyz", io.BytesIO(b"hello"), "text/plain")),
             ("files", ("empty.txt", io.BytesIO(b""), "text/plain")),
             ("files", ("ok.txt", io.BytesIO(b"The sky is blue on a clear day, and grass is green."), "text/plain"))]
    r = client.post("/api/documents", files=files).json()
    assert [x["ok"] for x in r["results"]] == [False, False, True]
    assert "Unsupported" in r["results"][0]["error"] and r["failed"] == 2


def test_rebuild_index_endpoint(loaded_client):
    info = loaded_client.post("/api/documents/rebuild-index?wait=true").json()
    assert info["state"] == "ready" and info["passages"] > 3 and info["documents"] == 3


# ------------------------------------------------------------------ claims + verify
def test_extract_claims_endpoint_and_validation(client):
    r = client.post("/api/claims/extract", json={"answer": ANSWER}).json()
    assert r["count"] == 4 and r["claims"][0]["id"] == "C1"
    assert client.post("/api/claims/extract", json={"answer": "   "}).status_code == 422
    assert client.post("/api/claims/extract", json={}).status_code == 422


def test_verify_requires_documents(client):
    r = client.post("/api/verify", json={"answer": ANSWER, "wait": True}).json()
    assert r["status"] == "failed" and "library is empty" in r["error"]


def test_verify_end_to_end_all_three_categories(loaded_client):
    s = loaded_client.post("/api/verify", json={"answer": ANSWER, "wait": True}).json()
    assert s["status"] == "completed", s.get("error")
    by_text = {c["text"]: c for c in s["claims"]}
    assert by_text["The Eiffel Tower was completed in 1889."]["status"] == "SUPPORTED"
    assert by_text["The Eiffel Tower is 150 metres tall."]["status"] == "CONTRADICTED"
    ins = [c for c in s["claims"] if c["status"] == "INSUFFICIENT_EVIDENCE"]
    assert ins and "Michelin" in ins[0]["text"]
    summ = s["summary"]
    assert summ["total_claims"] == 4 and summ["supported"] >= 2 and summ["contradicted"] == 1 and summ["insufficient"] == 1
    assert summ["processing_time"] > 0 and summ["documents_used"]
    c = by_text["The Eiffel Tower was completed in 1889."]
    ev = c["evidence"][0]
    assert ev["doc_name"] == "eiffel_tower_factsheet.txt" and ev["page"] == 1
    assert set(ev["nli"]) == {"entailment", "contradiction", "neutral"}
    assert ev["bm25_score"] is not None and ev["dense_score"] is not None and ev["fused_score"] > 0
    assert abs(sum(c["scores"].values()) - 1) < 1e-3 and c["explanation"]
    # NLI result drives the label, never retrieval similarity alone
    assert ev["relation"] in ("supports", "contradicts", "neutral")


def test_verify_with_user_edited_claims_and_document_selection(loaded_client):
    docs = loaded_client.get("/api/documents").json()["documents"]
    solar = next(d for d in docs if d["name"].startswith("solar"))
    s = loaded_client.post("/api/verify", json={
        "answer": "Mars facts", "claims": [{"id": "X1", "text": "Mars has two small moons, Phobos and Deimos."},
                                           {"text": "Mars has 3 moons."}],
        "document_ids": [solar["id"]], "wait": True}).json()
    assert s["status"] == "completed"
    assert [c["id"] for c in s["claims"]] == ["X1", "C2"]
    assert s["claims"][0]["status"] == "SUPPORTED" and s["claims"][1]["status"] == "CONTRADICTED"
    assert all(e["doc_name"] == solar["name"] for c in s["claims"] for e in c["evidence"])


def test_async_verification_progress_and_history(loaded_client):
    r = loaded_client.post("/api/verify", json={"answer": ANSWER})
    assert r.status_code == 202
    sid = r.json()["id"]
    for _ in range(100):
        s = loaded_client.get(f"/api/history/{sid}").json()
        if s["status"] in ("completed", "failed"):
            break
        time.sleep(0.1)
    assert s["status"] == "completed" and s["progress"]["stage"] == "done"
    hist = loaded_client.get("/api/history").json()
    assert hist["total"] == 1 and hist["sessions"][0]["id"] == sid
    assert "claims" not in hist["sessions"][0] and hist["sessions"][0]["summary"]["total_claims"] == 4
    assert loaded_client.delete(f"/api/history/{sid}").status_code == 200
    assert loaded_client.get(f"/api/history/{sid}").status_code == 404
    assert loaded_client.delete(f"/api/history/{sid}").status_code == 404


def test_clear_history_and_stats(loaded_client):
    for _ in range(2):
        loaded_client.post("/api/verify", json={"answer": ANSWER, "wait": True})
    st = loaded_client.get("/api/stats/overview").json()
    assert st["completed"] == 2 and st["claims"]["total_claims"] == 8 and st["documents"] == 3
    assert loaded_client.delete("/api/history").json()["deleted"] == 2
    assert loaded_client.get("/api/history").json()["total"] == 0


def test_no_checkable_claims_fails_cleanly(loaded_client):
    s = loaded_client.post("/api/verify", json={"answer": "Hi! What is up?", "wait": True}).json()
    assert s["status"] == "failed" and "No checkable" in s["error"]


def test_verify_validation_errors(client):
    assert client.post("/api/verify", json={"answer": ""}).status_code == 422
    assert client.post("/api/verify", json={"answer": "x" * 30001}).status_code == 422
    assert client.get("/api/history/doesnotexist").status_code == 404


def test_model_unavailable_returns_failed_session_with_instructions(loaded_client):
    loaded_client.app.state.services.models.nli = None
    loaded_client.app.state.services.models.status["nli"].update(state="error", message="Could not load NLI model 'x'.")
    s = loaded_client.post("/api/verify", json={"answer": ANSWER, "wait": True}).json()
    assert s["status"] == "failed" and "NLI model" in s["error"]


# ------------------------------------------------------------------------ settings
def test_settings_roundtrip_validation_and_reset(client):
    s = client.get("/api/settings").json()["settings"]
    assert s["entail_threshold"] == 0.7
    r = client.put("/api/settings", json={"entail_threshold": 0.8, "top_k": 3})
    assert r.status_code == 200 and r.json()["settings"]["top_k"] == 3 and r.json()["settings"]["nli_top_k"] == 3
    assert client.get("/api/settings").json()["settings"]["entail_threshold"] == 0.8
    assert client.put("/api/settings", json={"entail_threshold": 5}).status_code == 422
    assert client.put("/api/settings", json={"bogus": 1}).status_code == 422
    assert client.put("/api/settings", json={"theme": "purple"}).status_code == 422
    assert client.post("/api/settings/reset").json()["settings"]["entail_threshold"] == 0.7


def test_changing_threshold_changes_verdicts(loaded_client):
    claims = [{"text": "Mars has two small moons, Phobos and Deimos."}]
    base = loaded_client.post("/api/verify", json={"answer": "Mars", "claims": claims, "wait": True}).json()
    assert base["claims"][0]["status"] == "SUPPORTED"
    loaded_client.put("/api/settings", json={"entail_threshold": 0.95})
    strict = loaded_client.post("/api/verify", json={"answer": "Mars", "claims": claims, "wait": True}).json()
    assert strict["claims"][0]["status"] == "INSUFFICIENT_EVIDENCE"


def test_changing_chunk_size_rechunks_documents(loaded_client):
    before = loaded_client.get("/api/documents").json()["index"]["passages"]
    loaded_client.put("/api/settings", json={"chunk_words": 30})
    info = loaded_client.post("/api/documents/rebuild-index?wait=true").json()
    assert info["passages"] > before


# ------------------------------------------------------------------------- reports
def test_pdf_report_download(loaded_client):
    s = loaded_client.post("/api/verify", json={"answer": ANSWER, "wait": True}).json()
    r = loaded_client.get(f"/api/history/{s['id']}/report.pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content[:5] == b"%PDF-" and len(r.content) > 5000
    assert "attachment" in r.headers["content-disposition"]
    assert loaded_client.get("/api/history/nope/report.pdf").status_code == 404


def test_report_unavailable_until_completed(loaded_client):
    svc = loaded_client.app.state.services
    sid = svc.db.create_session(answer_text="x", document_ids=[], settings={}, title="x")
    assert loaded_client.get(f"/api/history/{sid}/report.pdf").status_code == 409


# ------------------------------------------------------------------------- samples / eval
def test_samples_endpoint(client):
    s = client.get("/api/samples").json()
    assert len(s["answers"]) == 3 and "solar_system_notes.pdf" in s["documents"]
    assert {e["label"] for a in s["answers"] for e in a["expected"]} == {"SUPPORTED", "CONTRADICTED", "INSUFFICIENT_EVIDENCE"}


def test_evaluation_without_data_gives_actionable_error(client):
    st = client.get("/api/evaluation/status").json()
    assert st["data"]["ready"] is False and "download_fever" in st["setup_hint"]
    r = client.post("/api/evaluation/run", json={})
    assert r.status_code == 400 and "download_fever" in r.json()["detail"]
    assert client.get("/api/evaluation/results").status_code == 404


def test_index_rebuilds_automatically_when_models_become_ready(paths):
    """Documents uploaded while models are still loading must be indexed once loading finishes."""
    from app.database import Database
    from app.main import build_services
    from app.services.embeddings import TfidfLsaEmbedder
    from app.services.library import ingest_file
    from app.services.managers import ModelManager, SettingsStore
    from helpers import StubNLI

    models = ModelManager(SettingsStore(Database(paths.db)), nli_factory=lambda s: StubNLI(),
                          embedder_factory=lambda s: TfidfLsaEmbedder())
    svc = build_services(paths, models)
    svc.models.on_ready.append(svc.index.rebuild_safe)       # what create_app registers
    ingest_file(svc, SAMPLES / "eiffel_tower_factsheet.txt", "eiffel_tower_factsheet.txt")
    svc.index.rebuild_safe()
    assert svc.index.info["state"] == "error"                # models not loaded yet
    models.load_all()                                        # loading finishes -> callback fires
    assert svc.index.info["state"] == "ready" and svc.index.info["passages"] >= 1
