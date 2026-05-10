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
