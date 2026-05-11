from fastapi.testclient import TestClient
from app.main import app
from app.db.database import init_db, get_db_connection

client = TestClient(app)

def test_health_check():
    # Make sure DB is initialized before health check
    init_db(get_db_connection())
    
    response = client.get("/health")
    
    # We expect 503 or 200 depending on Ollama, but it should return JSON
    assert response.status_code in [200, 503]
    data = response.json()
    assert "status" in data
    assert "components" in data
    assert "db" in data["components"]

def test_get_memories_empty():
    response = client.get("/api/v1/memories/user_test")
    assert response.status_code == 200
    assert response.json() == []

def test_get_history_empty():
    response = client.get("/api/v1/memories/user_test/history")
    assert response.status_code == 200
    assert response.json() == []

def test_get_conflicts_empty():
    response = client.get("/api/v1/memories/user_test/conflicts")
    assert response.status_code == 200
    assert response.json() == []

def test_ingest_session_validation_error():
    response = client.post("/api/v1/sessions", json={"bad": "payload"})
    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    assert data["error"] == "Validation Error"
    assert "detail" in data

def test_get_session_trace_not_found():
    response = client.get("/api/v1/sessions/ses_nonexistent/trace")
    assert response.status_code == 404
    assert response.json() == {"detail": "Session not found"}

def test_get_session_trace_success():
    # Insert a fake session and consolidation log directly to test the GET endpoint
    conn = get_db_connection()
    try:
        from app.db.models import Session, ConsolidationLog
        from app.db.queries import insert_session, log_consolidation_decision
        
        test_session_id = "ses_testtraceok"
        session = Session(
            id=test_session_id, user_id="test_user", raw_text="hi",
            extracted_count=1, add_count=1, duration_ms=150.0
        )
        insert_session(conn, session)
        
        log = ConsolidationLog(
            id="log_test1", user_id="test_user", session_id=test_session_id,
            new_memory_id="mem_test1", decision="ADD", similarity_score=0.9,
            llm_called=1, reasoning="Seemed good", extracted_content="I am a dummy",
            extracted_type="fact", confidence=0.99, threshold=0.82, extraction_index=0
        )
        log_consolidation_decision(conn, log)
        conn.commit()
    finally:
        conn.close()

    response = client.get(f"/api/v1/sessions/{test_session_id}/trace")
    assert response.status_code == 200
    
    data = response.json()
    assert data["session_id"] == test_session_id
    assert data["duration_ms"] == 150.0
    assert data["llm_calls"] == 1
    assert len(data["steps"]) == 1
    
    step = data["steps"][0]
    assert step["memory_content"] == "I am a dummy"
    assert step["decision"] == "ADD"
    assert step["confidence"] == 0.99
