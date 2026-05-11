from pydantic import BaseModel, ConfigDict
from typing import List, Literal, Optional
from datetime import datetime

# Request Models
class IngestSessionRequest(BaseModel):
    user_id: str
    conversation: str

class ThresholdSweepRequest(BaseModel):
    sessions: List[str]
    thresholds: List[float]
    user_id: str = "sweep_test_user"

# Response Models
class MemoryRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    user_id: str
    content: str
    memory_type: str
    status: str
    source: str
    confidence: float
    session_id: str
    superseded_by: Optional[str] = None
    created_at: datetime
    accessed_at: datetime

class ConflictRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    memory_id_a: MemoryRecord
    memory_id_b: MemoryRecord
    similarity_score: float
    resolved: int
    created_at: datetime

class IngestionResult(BaseModel):
    session_id: str
    user_id: str
    extracted: int
    add: int
    noop: int
    update: int
    conflict: int
    skipped: int
    duration_ms: float

class TraceStep(BaseModel):
    order: int
    memory_content: str
    memory_type: str
    confidence: float
    similarity: Optional[float] = None
    threshold: float
    decision: str
    matched_memory_id: Optional[str] = None
    superseded_memory_id: Optional[str] = None

class SessionTrace(BaseModel):
    session_id: str
    duration_ms: float
    llm_calls: int
    steps: List[TraceStep]
    duration_ms: float

class ThresholdSweepResult(BaseModel):
    threshold: float
    false_merges: int
    missed_conflicts: int
    final_active_count: int
    total_llm_calls: int

class ThresholdSweepResponse(BaseModel):
    results: List[ThresholdSweepResult]
    sessions_processed: int
    duration_ms: float
