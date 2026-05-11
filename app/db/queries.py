import sqlite3
from typing import Iterator, List, Optional
from app.db.models import Memory, Session, Conflict, ConsolidationLog

def _row_to_memory(row: sqlite3.Row) -> Memory:
    return Memory(
        id=row['id'],
        user_id=row['user_id'],
        content=row['content'],
        memory_type=row['memory_type'],
        status=row['status'],
        source=row['source'],
        confidence=row['confidence'],
        embedding=row['embedding'],
        session_id=row['session_id'],
        superseded_by=row['superseded_by'],
        created_at=row['created_at'],
        accessed_at=row['accessed_at']
    )

def _row_to_session(row: sqlite3.Row) -> Session:
    return Session(
        id=row['id'],
        user_id=row['user_id'],
        raw_text=row['raw_text'],
        extracted_count=row['extracted_count'],
        add_count=row['add_count'],
        noop_count=row['noop_count'],
        update_count=row['update_count'],
        conflict_count=row['conflict_count'],
        skipped_count=row['skipped_count'],
        duration_ms=row['duration_ms'],
        created_at=row['created_at']
    )

def _row_to_conflict(row: sqlite3.Row) -> Conflict:
    return Conflict(
        id=row['id'],
        user_id=row['user_id'],
        memory_id_a=row['memory_id_a'],
        memory_id_b=row['memory_id_b'],
        similarity_score=row['similarity_score'],
        resolved=row['resolved'],
        created_at=row['created_at']
    )

def _row_to_consolidation_log(row: sqlite3.Row) -> ConsolidationLog:
    return ConsolidationLog(
        id=row['id'],
        user_id=row['user_id'],
        session_id=row['session_id'],
        new_memory_id=row['new_memory_id'],
        decision=row['decision'],
        existing_memory_id=row['existing_memory_id'],
        matched_memory_id=row['matched_memory_id'],
        similarity_score=row['similarity_score'],
        llm_called=row['llm_called'],
        reasoning=row['reasoning'],
        extracted_content=row['extracted_content'],
        extracted_type=row['extracted_type'],
        confidence=row['confidence'],
        threshold=row['threshold'],
        extraction_index=row['extraction_index'],
        created_at=row['created_at']
    )

def get_active_memories(conn: sqlite3.Connection, user_id: str, memory_type: Optional[str] = None, sort: str = "created_at_desc", limit: int = 100, offset: int = 0) -> List[Memory]:
    """Fetch active memories for a given user, with pagination, sorting, and optional type filtering."""
    query = "SELECT * FROM memories WHERE user_id = ? AND status = 'active'"
    params = [user_id]

    if memory_type:
        query += " AND memory_type = ?"
        params.append(memory_type)

    if sort == "created_at_asc":
        query += " ORDER BY created_at ASC"
    elif sort == "confidence_desc":
        query += " ORDER BY confidence DESC"
    else:
        query += " ORDER BY created_at DESC"

    query += " LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor = conn.execute(query, params)
    return [_row_to_memory(row) for row in cursor]

def update_accessed_at(conn: sqlite3.Connection, memory_ids: List[str]):
    """Update accessed_at for a list of memory IDs."""
    if not memory_ids:
        return
    query = f"UPDATE memories SET accessed_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id IN ({','.join(['?'] * len(memory_ids))})"
    conn.execute(query, memory_ids)

def get_memory_history(conn: sqlite3.Connection, user_id: str, status: str = "all", memory_type: Optional[str] = None) -> List[Memory]:
    """Fetch complete memory history for a user."""
    query = "SELECT * FROM memories WHERE user_id = ?"
    params = [user_id]

    if status != "all":
        query += " AND status = ?"
        params.append(status)
        
    if memory_type:
        query += " AND memory_type = ?"
        params.append(memory_type)

    query += " ORDER BY created_at DESC"
    cursor = conn.execute(query, params)
    return [_row_to_memory(row) for row in cursor]

def get_conflicts(conn: sqlite3.Connection, user_id: str, resolved: bool = False) -> List[Conflict]:
    """Fetch unresolved conflict pairs for a user."""
    query = "SELECT * FROM conflicts WHERE user_id = ? AND resolved = ?"
    params = [user_id, 1 if resolved else 0]
    cursor = conn.execute(query, params)
    return [_row_to_conflict(row) for row in cursor]

def get_memory_by_id(conn: sqlite3.Connection, memory_id: str) -> Optional[Memory]:
    """Fetch a single memory by ID."""
    cursor = conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,))
    row = cursor.fetchone()
    return _row_to_memory(row) if row else None

def get_session_by_id(conn: sqlite3.Connection, session_id: str) -> Optional[Session]:
    """Fetch a single session by ID."""
    cursor = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
    row = cursor.fetchone()
    return _row_to_session(row) if row else None

def get_consolidation_logs_by_session(conn: sqlite3.Connection, session_id: str) -> List[ConsolidationLog]:
    """Fetch all consolidation logs for a given session."""
    query = "SELECT * FROM consolidation_log WHERE session_id = ? ORDER BY extraction_index ASC"
    cursor = conn.execute(query, (session_id,))
    return [_row_to_consolidation_log(row) for row in cursor]

def insert_memory(conn: sqlite3.Connection, memory: Memory):
    """Insert a new memory into the database."""
    query = """
    INSERT INTO memories (id, user_id, content, memory_type, status, source, confidence, embedding, session_id)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    conn.execute(query, (
        memory.id, memory.user_id, memory.content, memory.memory_type,
        memory.status, memory.source, memory.confidence, memory.embedding, memory.session_id
    ))

def mark_superseded(conn: sqlite3.Connection, memory_id: str, superseded_by: str):
    """Mark an existing memory as superseded by a new memory."""
    query = "UPDATE memories SET status = 'superseded', superseded_by = ? WHERE id = ?"
    conn.execute(query, (superseded_by, memory_id))

def insert_conflict(conn: sqlite3.Connection, conflict: Conflict):
    """Insert a new conflict record."""
    query = """
    INSERT INTO conflicts (id, user_id, memory_id_a, memory_id_b, similarity_score, resolved)
    VALUES (?, ?, ?, ?, ?, ?)
    """
    conn.execute(query, (
        conflict.id, conflict.user_id, conflict.memory_id_a, conflict.memory_id_b,
        conflict.similarity_score, conflict.resolved
    ))

def log_consolidation_decision(conn: sqlite3.Connection, log: ConsolidationLog):
    """Insert a consolidation tracking log."""
    query = """
    INSERT INTO consolidation_log 
    (id, user_id, session_id, new_memory_id, decision, existing_memory_id, matched_memory_id, similarity_score, llm_called, reasoning, extracted_content, extracted_type, confidence, threshold, extraction_index)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    conn.execute(query, (
        log.id, log.user_id, log.session_id, log.new_memory_id, log.decision, log.existing_memory_id,
        log.matched_memory_id, log.similarity_score, log.llm_called, log.reasoning,
        log.extracted_content, log.extracted_type, log.confidence, log.threshold, log.extraction_index
    ))

def insert_session(conn: sqlite3.Connection, session: Session):
    """Insert a session tracking record."""
    query = """
    INSERT INTO sessions 
    (id, user_id, raw_text, extracted_count, add_count, noop_count, update_count, conflict_count, skipped_count, duration_ms)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    conn.execute(query, (
        session.id, session.user_id, session.raw_text, session.extracted_count,
        session.add_count, session.noop_count, session.update_count,
        session.conflict_count, session.skipped_count, session.duration_ms
    ))
