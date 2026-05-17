import requests
from typing import Dict, Any, Optional, List, Union

from config import API_BASE_URL


def _request(method: str, endpoint: str, *, json_data: Optional[Dict[str, Any]] = None, timeout: int = 30) -> Dict[str, Any]:
    """Execute an HTTP request and normalize the response for UI consumption."""
    try:
        response = requests.request(
            method,
            f"{API_BASE_URL}{endpoint}",
            json=json_data,
            timeout=timeout,
        )
        response.raise_for_status()

        try:
            payload = response.json()
        except ValueError:
            payload = None

        return {
            "ok": True,
            "status_code": response.status_code,
            "data": payload,
            "error": None,
        }
    except requests.exceptions.RequestException as exc:
        response = getattr(exc, "response", None)
        return {
            "ok": False,
            "status_code": getattr(response, "status_code", None),
            "data": None,
            "error": str(exc),
        }

def _get(endpoint: str) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
    """Helper for GET requests to the backend API."""
    try:
        response = requests.get(f"{API_BASE_URL}{endpoint}", timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API GET Error ({endpoint}): {e}")
        return None

def _post(endpoint: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Helper for POST requests to the backend API."""
    try:
        response = requests.post(f"{API_BASE_URL}{endpoint}", json=data, timeout=180)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API POST Error ({endpoint}): {e}")
        return None

def ingest_session(user_id: str, conversation: str) -> Optional[Dict[str, Any]]:
    """Submit a conversation session for ingestion and consolidation."""
    payload = {
        "user_id": user_id,
        "conversation": conversation
    }
    return _post("/sessions", payload)


def ingest_session_result(user_id: str, conversation: str) -> Dict[str, Any]:
    """Submit a session and return a normalized request result."""
    payload = {
        "user_id": user_id,
        "conversation": conversation,
    }
    return _request("POST", "/sessions", json_data=payload, timeout=180)

def ingest_batch_sessions(user_id: str, sessions: List[str]) -> Dict[str, Any]:
    """Ingest multiple sessions sequentially. Used for batch ingestion."""
    result = {
        "total": len(sessions),
        "successful": 0,
        "failed": 0,
        "session_ids": [],
        "errors": []
    }
    
    for i, sess in enumerate(sessions):
        res = ingest_session_result(user_id, sess)
        data = res.get("data") if isinstance(res, dict) else None
        if res.get("ok") and isinstance(data, dict) and data.get("session_id"):
            result["successful"] += 1
            result["session_ids"].append(data.get("session_id"))
        else:
            result["failed"] += 1
            result["errors"].append({"session_index": i, "error": res.get("error") or "API response empty or missing session_id"})
            
    return result


def fetch_active_memories(user_id: str) -> Dict[str, Any]:
    """Fetch active memories with normalized success/error metadata."""
    return _request("GET", f"/memories/{user_id}")


def fetch_memory_history(user_id: str) -> Dict[str, Any]:
    """Fetch memory history with normalized success/error metadata."""
    return _request("GET", f"/memories/{user_id}/history")


def fetch_conflicts(user_id: str) -> Dict[str, Any]:
    """Fetch unresolved conflicts with normalized success/error metadata."""
    return _request("GET", f"/memories/{user_id}/conflicts")


def fetch_session_trace(session_id: str) -> Dict[str, Any]:
    """Fetch pipeline trace with normalized success/error metadata."""
    return _request("GET", f"/sessions/{session_id}/trace")


def fetch_threshold_sweep() -> Dict[str, Any]:
    """Run the threshold sweep with normalized success/error metadata."""
    return _request("POST", "/admin/threshold-sweep", timeout=600)

def get_active_memories(user_id: str) -> List[Dict[str, Any]]:
    """Fetch active memories for the user."""
    res = _get(f"/memories/{user_id}")
    return res if isinstance(res, list) else []

def get_memory_history(user_id: str) -> List[Dict[str, Any]]:
    """Fetch memory history (lineage) for the user."""
    res = _get(f"/memories/{user_id}/history")
    return res if isinstance(res, list) else []

def get_conflicts(user_id: str) -> List[Dict[str, Any]]:
    """Fetch unresolved conflicts for the user."""
    res = _get(f"/memories/{user_id}/conflicts")
    return res if isinstance(res, list) else []

def get_session_trace(session_id: str) -> Optional[Dict[str, Any]]:
    """Fetch pipeline trace for a given session."""
    res = _get(f"/sessions/{session_id}/trace")
    return res if isinstance(res, dict) else None

def run_threshold_sweep() -> Optional[Dict[str, Any]]:
    """Execute a threshold sweep on the backend."""
    # Custom post request here because we need a longer timeout
    try:
        response = requests.post(f"{API_BASE_URL}/admin/threshold-sweep", timeout=600)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error executing POST to /admin/threshold-sweep: {e}")
        return None
