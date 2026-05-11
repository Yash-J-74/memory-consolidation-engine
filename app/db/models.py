from dataclasses import dataclass
from typing import Optional
from datetime import datetime
import numpy as np

@dataclass
class Memory:
    id: str
    user_id: str
    content: str
    memory_type: str
    status: str
    source: str
    confidence: float
    embedding: np.ndarray
    session_id: str
    superseded_by: Optional[str] = None
    created_at: Optional[str] = None
    accessed_at: Optional[str] = None

@dataclass
class Session:
    id: str
    user_id: str
    raw_text: str
    extracted_count: int = 0
    add_count: int = 0
    noop_count: int = 0
    update_count: int = 0
    conflict_count: int = 0
    skipped_count: int = 0
    duration_ms: float = 0.0
    created_at: Optional[str] = None

@dataclass
class Conflict:
    id: str
    user_id: str
    memory_id_a: str
    memory_id_b: str
    similarity_score: float
    resolved: int = 0
    created_at: Optional[str] = None

@dataclass
class ConsolidationLog:
    id: str
    user_id: str
    session_id: str
    new_memory_id: str
    decision: str
    existing_memory_id: Optional[str] = None
    matched_memory_id: Optional[str] = None
    similarity_score: Optional[float] = None
    llm_called: int = 0
    reasoning: Optional[str] = None
    extracted_content: str = ""
    extracted_type: str = ""
    confidence: float = 0.0
    threshold: float = 0.82
    extraction_index: int = 0
    created_at: Optional[str] = None
