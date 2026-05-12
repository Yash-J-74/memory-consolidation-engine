import json
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.api import ThresholdSweepRequest, ThresholdSweepResponse, ThresholdSweepResult
from app.core.logger import logger
from app.db.database import get_db_connection, init_db
from app.db.models import Conflict, ConsolidationLog, Memory
from app.db.queries import get_active_memories, insert_conflict, insert_memory, log_consolidation_decision, mark_superseded
from app.pipelines.consolidation import ConsolidationPipeline
from app.pipelines.extraction import ExtractionPipeline
from app.services.embedder import encode

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def _load_ground_truth() -> list[dict]:
    fixture_path = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "sweep_ground_truth.json"
    try:
        with fixture_path.open("r", encoding="utf-8") as fixture_file:
            payload = json.load(fixture_file)
        return payload.get("sessions", [])
    except Exception as exc:
        logger.warning("Could not load sweep_ground_truth.json", error=str(exc))
        return []


GROUND_TRUTH = _load_ground_truth()


def _decision_value(decision) -> str:
    return str(getattr(decision, "value", decision))


@router.post("/threshold-sweep", response_model=ThresholdSweepResponse)
async def threshold_sweep(request: ThresholdSweepRequest):
    if not GROUND_TRUTH:
        raise HTTPException(status_code=500, detail="Ground truth fixture is not available.")

    if len(request.sessions) != len(GROUND_TRUTH):
        raise HTTPException(status_code=400, detail="Number of sessions must match ground truth length.")

    extraction_pipeline = ExtractionPipeline()
    consolidation_pipeline = ConsolidationPipeline()
    start_time = time.time()
    results: list[ThresholdSweepResult] = []

    for threshold in request.thresholds:
        conn = get_db_connection(":memory:")
        init_db(conn)

        false_merges = 0
        missed_conflicts = 0
        total_llm_calls = 0

        for session_index, session_text in enumerate(request.sessions):
            expected_memories = GROUND_TRUTH[session_index].get("expected_memories", [])

            try:
                extracted_memories = await extraction_pipeline.run(session_text)
            except Exception as exc:
                logger.error("Extraction failed for sweep session", session_index=session_index, error=str(exc))
                extracted_memories = []

            for extraction_index, extracted_memory in enumerate(extracted_memories):
                candidates = list(
                    get_active_memories(
                        conn,
                        request.user_id,
                        memory_type=extracted_memory.memory_type,
                        limit=10000,
                    )
                )

                result = await consolidation_pipeline.run(extracted_memory, candidates, threshold=threshold)
                decision = _decision_value(result.decision)
                existing_memory_id = result.existing_memory_id or ""
                similarity_score = result.similarity_score if result.similarity_score is not None else 0.0
                embedding = result.embedding if result.embedding is not None else encode(extracted_memory.content)
                new_memory_id = f"mem_{uuid.uuid4().hex[:12]}"

                if decision == "ADD":
                    insert_memory(
                        conn,
                        Memory(
                            id=new_memory_id,
                            user_id=request.user_id,
                            content=extracted_memory.content,
                            memory_type=extracted_memory.memory_type,
                            status="active",
                            source=extracted_memory.source,
                            confidence=extracted_memory.confidence,
                            embedding=embedding,
                            session_id=f"sweep_{session_index}",
                            superseded_by=None,
                            created_at=None,
                            accessed_at=None,
                        ),
                    )
                elif decision == "UPDATE":
                    if result.existing_memory_id:
                        mark_superseded(conn, result.existing_memory_id, new_memory_id)
                    insert_memory(
                        conn,
                        Memory(
                            id=new_memory_id,
                            user_id=request.user_id,
                            content=extracted_memory.content,
                            memory_type=extracted_memory.memory_type,
                            status="active",
                            source=extracted_memory.source,
                            confidence=extracted_memory.confidence,
                            embedding=embedding,
                            session_id=f"sweep_{session_index}",
                            superseded_by=None,
                            created_at=None,
                            accessed_at=None,
                        ),
                    )
                elif decision == "CONFLICT":
                    insert_memory(
                        conn,
                        Memory(
                            id=new_memory_id,
                            user_id=request.user_id,
                            content=extracted_memory.content,
                            memory_type=extracted_memory.memory_type,
                            status="active",
                            source=extracted_memory.source,
                            confidence=extracted_memory.confidence,
                            embedding=embedding,
                            session_id=f"sweep_{session_index}",
                            superseded_by=None,
                            created_at=None,
                            accessed_at=None,
                        ),
                    )
                    insert_conflict(
                        conn,
                        Conflict(
                            id=f"con_{uuid.uuid4().hex[:12]}",
                            user_id=request.user_id,
                            memory_id_a=existing_memory_id or new_memory_id,
                            memory_id_b=new_memory_id,
                            similarity_score=similarity_score,
                            resolved=0,
                            created_at=None,
                        ),
                    )

                log_consolidation_decision(
                    conn,
                    ConsolidationLog(
                        id=f"log_{uuid.uuid4().hex[:12]}",
                        user_id=request.user_id,
                        session_id=f"sweep_{session_index}",
                        new_memory_id=new_memory_id if decision != "NOOP" else "disposed",
                        decision=decision,
                        existing_memory_id=result.existing_memory_id,
                        similarity_score=similarity_score,
                        llm_called=1 if result.llm_called else 0,
                        reasoning=result.reasoning or "",
                        extraction_index=extraction_index,
                        created_at=None,
                    ),
                )

                total_llm_calls += 1 if result.llm_called else 0

                expected_decision = "ADD"
                if extraction_index < len(expected_memories):
                    expected_decision = expected_memories[extraction_index].get("expected_decision", "ADD")

                if expected_decision == "ADD" and decision in {"NOOP", "UPDATE"}:
                    false_merges += 1
                if expected_decision == "CONFLICT" and decision in {"ADD", "UPDATE"}:
                    missed_conflicts += 1

            conn.commit()

        active_memories = list(get_active_memories(conn, request.user_id, limit=10000))
        results.append(
            ThresholdSweepResult(
                threshold=threshold,
                false_merges=false_merges,
                missed_conflicts=missed_conflicts,
                final_active_count=len(active_memories),
                total_llm_calls=total_llm_calls,
            )
        )
        conn.close()

    return ThresholdSweepResponse(
        results=results,
        sessions_processed=len(request.sessions),
        duration_ms=(time.time() - start_time) * 1000,
    )