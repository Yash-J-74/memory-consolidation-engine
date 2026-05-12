import requests
from typing import Dict, Any, Optional, List, Union

from config import API_BASE_URL

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
