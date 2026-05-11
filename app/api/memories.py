from fastapi import APIRouter, Depends, Query, BackgroundTasks, HTTPException
from typing import List, Optional
import sqlite3

from app.api import MemoryRecord, ConflictRecord
from app.db.database import get_db
from app.db.queries import get_active_memories, get_memory_history, get_conflicts, update_accessed_at, get_memory_by_id
from app.core.logger import logger

router = APIRouter(prefix="/api/v1/memories", tags=["memories"])

def update_access_time_bg(db_path: str, memory_ids: List[str]):
    # Since we can't reuse the same connection on a different thread in sqlite without checking,
    # it's safer to get a new short-lived connection or just use the same one if WAL config etc.
    # In SQLite, BackgroundTasks runs on a worker thread. We need a new connection.
    # We will import get_db_connection directly.
    from app.db.database import get_db_connection
    conn = get_db_connection(db_path)
    try:
        if memory_ids:
            query = f"UPDATE memories SET accessed_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id IN ({','.join(['?'] * len(memory_ids))})"
            conn.execute(query, memory_ids)
            conn.commit()
    except Exception as e:
        logger.error(f"Background access time save failed: {e}")
    finally:
        conn.close()

@router.get("/{user_id}", response_model=List[MemoryRecord])
async def get_memories(
    user_id: str,
    background_tasks: BackgroundTasks,
    memory_type: Optional[str] = None,
    sort: str = Query("created_at_desc", pattern="^(created_at_asc|created_at_desc|confidence_desc)$"),
    limit: int = 100,
    offset: int = 0,
    db: sqlite3.Connection = Depends(get_db)
):
    memories = get_active_memories(db, user_id, memory_type, sort, limit, offset)
    
    # Extract IDs to update
    memory_ids = [m.id for m in memories]
    
    if memory_ids:
        from app.core.config import settings
        background_tasks.add_task(update_access_time_bg, settings.DATABASE_PATH, memory_ids)

    return memories

@router.get("/{user_id}/history", response_model=List[MemoryRecord])
async def get_history(
    user_id: str,
    status: str = Query("all", pattern="^(active|superseded|all)$"),
    memory_type: Optional[str] = None,
    db: sqlite3.Connection = Depends(get_db)
):
    memories = get_memory_history(db, user_id, status, memory_type)
    return memories

@router.get("/{user_id}/conflicts", response_model=List[ConflictRecord]) # Returns Conflict records combined with memory bodies if needed, or we can have a separate endpoint to get conflict details by ID if we want to keep this light.
async def get_user_conflicts(
    user_id: str,
    resolved: bool = False,
    db: sqlite3.Connection = Depends(get_db)
):
    # Format for conflicts endpoint (with embedded MemoryRecord)
    conflicts_db = get_conflicts(db, user_id, resolved)
    results = []
    for c in conflicts_db:
        ma = get_memory_by_id(db, c.memory_id_a)
        mb = get_memory_by_id(db, c.memory_id_b)
        results.append({
            "id": c.id,
            "user_id": c.user_id,
            "memory_id_a": ma,
            "memory_id_b": mb,
            "similarity_score": c.similarity_score,
            "resolved": bool(c.resolved),
            "created_at": c.created_at
        })
    return results
