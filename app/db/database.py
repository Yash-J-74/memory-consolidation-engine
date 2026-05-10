import sqlite3
import numpy as np
from app.core.config import settings

def adapt_array(arr):
    """Serialize numpy ndarray into a BLOB for SQLite."""
    return arr.tobytes()

def convert_array(text):
    """Deserialize BLOB back into numpy array."""
    return np.frombuffer(text, dtype=np.float32)

# Register SQLite adapters and converters for numpy arrays
sqlite3.register_adapter(np.ndarray, adapt_array)
sqlite3.register_converter("ARRAY", convert_array)

def get_db_connection(db_path: str = None) -> sqlite3.Connection:
    """Creates a new database connection."""
    path = db_path if db_path is not None else settings.DATABASE_PATH
    conn = sqlite3.connect(
        path,
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    return conn

def init_db(conn: sqlite3.Connection):
    """Initializes the database schema and creates necessary indices."""
    schema = """
    -- Core memory record table
    CREATE TABLE IF NOT EXISTS memories (
        id              TEXT PRIMARY KEY,
        user_id         TEXT NOT NULL,
        content         TEXT NOT NULL,
        memory_type     TEXT NOT NULL CHECK (memory_type IN ('preference', 'fact', 'event')),
        status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'superseded')),
        source          TEXT NOT NULL CHECK (source IN ('user_stated', 'agent_inferred')),
        confidence      REAL NOT NULL,
        embedding       ARRAY NOT NULL,
        session_id      TEXT NOT NULL,
        superseded_by   TEXT,
        created_at      DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
        accessed_at     DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
    );

    -- Session tracking
    CREATE TABLE IF NOT EXISTS sessions (
        id              TEXT PRIMARY KEY,
        user_id         TEXT NOT NULL,
        raw_text        TEXT NOT NULL,
        extracted_count INTEGER NOT NULL DEFAULT 0,
        add_count       INTEGER NOT NULL DEFAULT 0,
        noop_count      INTEGER NOT NULL DEFAULT 0,
        update_count    INTEGER NOT NULL DEFAULT 0,
        conflict_count  INTEGER NOT NULL DEFAULT 0,
        skipped_count   INTEGER NOT NULL DEFAULT 0,
        created_at      DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
    );

    -- Conflict pairs
    CREATE TABLE IF NOT EXISTS conflicts (
        id              TEXT PRIMARY KEY,
        user_id         TEXT NOT NULL,
        memory_id_a     TEXT NOT NULL,
        memory_id_b     TEXT NOT NULL,
        similarity_score REAL NOT NULL,
        resolved        INTEGER NOT NULL DEFAULT 0,
        created_at      DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
    );

    -- Consolidation decision log
    CREATE TABLE IF NOT EXISTS consolidation_log (
        id              TEXT PRIMARY KEY,
        user_id         TEXT NOT NULL,
        new_memory_id   TEXT NOT NULL,
        existing_memory_id TEXT,
        similarity_score REAL,
        decision        TEXT NOT NULL CHECK (decision IN ('ADD', 'NOOP', 'UPDATE', 'CONFLICT')),
        llm_called      INTEGER NOT NULL DEFAULT 0,
        reasoning       TEXT,
        extraction_index INTEGER NOT NULL DEFAULT 0,
        created_at      DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
    );

    -- Indexes
    CREATE INDEX IF NOT EXISTS idx_memories_user_type_status
        ON memories (user_id, memory_type, status);
    
    CREATE INDEX IF NOT EXISTS idx_memories_user_status
        ON memories (user_id, status);

    CREATE INDEX IF NOT EXISTS idx_conflicts_user_resolved
        ON conflicts (user_id, resolved);
    """
    conn.executescript(schema)
    conn.commit()

def get_db():
    """FastAPI dependency for database connections."""
    conn = get_db_connection()
    try:
        yield conn
    finally:
        conn.close()
