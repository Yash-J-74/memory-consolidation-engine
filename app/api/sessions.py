import time
import uuid
import sqlite3
from fastapi import APIRouter, Depends, HTTPException
from typing import List

from app.api import IngestSessionRequest, IngestionResult
from app.db.database import get_db
from app.pipelines.extraction import ExtractionPipeline
from app.pipelines.consolidation import ConsolidationPipeline
from app.db.models import Session, Memory, Conflict, ConsolidationLog
from app.db.queries import insert_session, insert_memory, mark_superseded, insert_conflict, log_consolidation_decision, get_active_memories
from app.core.logger import logger

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])

@router.post("", response_model=IngestionResult)
async def ingest_session(
    request: IngestSessionRequest,
    db: sqlite3.Connection = Depends(get_db)
):
    start_time = time.time()
    session_id = f"ses_{uuid.uuid4().hex[:8]}"
    
    # 1. Extraction Pipeline
    extraction_pipeline = ExtractionPipeline()
    extracted_memories = await extraction_pipeline.run(request.conversation)
    
    # If LLM barfed entirely and raised, we let it propagate as 500.
    
    counts = {
        "extracted": len(extracted_memories),
        "add": 0,
        "noop": 0,
        "update": 0,
        "conflict": 0,
        "skipped": 0 # We skip tracking pipeline skips since pipeline already filtered them before returning. We only track skipped if something fails here.
    }
    
    consolidation_pipeline = ConsolidationPipeline()

    for idx, ext_mem in enumerate(extracted_memories):
        try:
            # 2. Consolidation Pipeline

            # Convert DB returned Memories to what pipeline expects, pipeline expects a list of Memory objects.
            candidates = list(get_active_memories(db, request.user_id, memory_type=ext_mem.memory_type, limit=10000))
            
            result = await consolidation_pipeline.run(ext_mem, candidates)
            
            new_memory_id = f"mem_{uuid.uuid4().hex[:12]}"
            
            # 3. DB Actions based on decision
            if result.decision == "ADD":
                memory_db = Memory(
                    id=new_memory_id,
                    user_id=request.user_id,
                    content=ext_mem.content,
                    memory_type=ext_mem.memory_type,
                    status="active",
                    source=ext_mem.source,
                    confidence=ext_mem.confidence,
                    embedding=result.embedding,
                    session_id=session_id,
                    superseded_by=None,
                    created_at=None, # auto generated in db by DEFAULT
                    accessed_at=None # auto generated
                )
                insert_memory(db, memory_db)
                counts["add"] += 1
                
            elif result.decision == "NOOP":
                counts["noop"] += 1
                
            elif result.decision == "UPDATE":
                # Mark existing as superseded
                mark_superseded(db, result.existing_memory_id, new_memory_id)
                # Insert new memory
                memory_db = Memory(
                    id=new_memory_id,
                    user_id=request.user_id,
                    content=ext_mem.content,
                    memory_type=ext_mem.memory_type,
                    status="active",
                    source=ext_mem.source,
                    confidence=ext_mem.confidence,
                    embedding=result.embedding,
                    session_id=session_id,
                    superseded_by=None,
                    created_at=None,
                    accessed_at=None
                )
                insert_memory(db, memory_db)
                counts["update"] += 1
                
            elif result.decision == "CONFLICT":
                # Insert new memory
                memory_db = Memory(
                    id=new_memory_id,
                    user_id=request.user_id,
                    content=ext_mem.content,
                    memory_type=ext_mem.memory_type,
                    status="active",
                    source=ext_mem.source,
                    confidence=ext_mem.confidence,
                    embedding=result.embedding,
                    session_id=session_id,
                    superseded_by=None,
                    created_at=None,
                    accessed_at=None
                )
                insert_memory(db, memory_db)
                
                # Create conflict
                conflict = Conflict(
                    id=f"con_{uuid.uuid4().hex[:12]}",
                    user_id=request.user_id,
                    memory_id_a=result.existing_memory_id,
                    memory_id_b=new_memory_id,
                    similarity_score=result.similarity_score,
                    resolved=0,
                    created_at=None
                )
                insert_conflict(db, conflict)
                counts["conflict"] += 1

            # 4. Audit Log
            log = ConsolidationLog(
                id=f"log_{uuid.uuid4().hex[:12]}",
                user_id=request.user_id,
                new_memory_id=new_memory_id if result.decision != "NOOP" else "disposed",
                decision=result.decision,
                existing_memory_id=result.existing_memory_id,
                similarity_score=result.similarity_score or 0.0,
                llm_called=1 if result.llm_called else 0,
                reasoning=result.reasoning or "",
                extraction_index=idx,
                created_at=None
            )
            log_consolidation_decision(db, log)
            db.commit()
            
        except Exception as e:
            db.rollback()
            logger.error(
                "Memory processing failed",
                user_id=request.user_id,
                content=ext_mem.content if ext_mem else "unknown",
                error=str(e),
                exc_info=True   # includes full traceback in structured log
            )
            counts["skipped"] += 1

    duration_ms = (time.time() - start_time) * 1000

    # Record Session
    session_record = Session(
        id=session_id,
        user_id=request.user_id,
        raw_text=request.conversation,
        extracted_count=counts["extracted"],
        add_count=counts["add"],
        noop_count=counts["noop"],
        update_count=counts["update"],
        conflict_count=counts["conflict"],
        skipped_count=counts["skipped"],
        created_at=None
    )
    insert_session(db, session_record)
    db.commit()

    return IngestionResult(
        session_id=session_id,
        user_id=request.user_id,
        extracted=counts["extracted"],
        add=counts["add"],
        noop=counts["noop"],
        update=counts["update"],
        conflict=counts["conflict"],
        skipped=counts["skipped"],
        duration_ms=duration_ms
    )
