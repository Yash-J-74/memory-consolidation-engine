import asyncio
import uuid

import numpy as np

from app.db.models import Memory
from app.pipelines.consolidation import ConsolidationDecision, ConsolidationPipeline
from app.pipelines.extraction import ExtractedMemory


def _memory(content: str, embedding: np.ndarray, memory_type: str = "preference") -> Memory:
	return Memory(
		id=str(uuid.uuid4()),
		user_id="user_001",
		content=content,
		memory_type=memory_type,
		status="active",
		source="user_stated",
		confidence=0.95,
		embedding=embedding.astype(np.float32),
		session_id=str(uuid.uuid4()),
	)


def test_consolidation_returns_add_when_no_existing_memories():
	pipeline = ConsolidationPipeline(encoder=lambda _: np.array([1.0, 0.0], dtype=np.float32))
	new_memory = ExtractedMemory(
		content="User prefers email communication.",
		memory_type="preference",
		confidence=0.90,
		source="user_stated",
	)

	result = asyncio.run(pipeline.run(new_memory, []))

	assert result.decision == ConsolidationDecision.ADD
	assert result.llm_called is False


def test_consolidation_below_threshold_skips_llm_and_adds():
	llm_called = {"value": False}

	async def fake_completion(prompt: str, temperature: float) -> str:
		llm_called["value"] = True
		return "{}"

	pipeline = ConsolidationPipeline(
		threshold=0.82,
		encoder=lambda _: np.array([1.0, 0.0], dtype=np.float32),
		completion_func=fake_completion,
		json_parser=lambda _: {"decision": "NOOP", "reasoning": "duplicate"},
	)
	existing = [_memory("Existing memory", np.array([0.0, 1.0], dtype=np.float32))]
	new_memory = {"content": "Completely different memory"}

	result = asyncio.run(pipeline.run(new_memory, existing))

	assert result.decision == ConsolidationDecision.ADD
	assert result.llm_called is False
	assert llm_called["value"] is False


def test_consolidation_above_threshold_uses_llm_decision():
	async def fake_completion(prompt: str, temperature: float) -> str:
		return '{"decision": "NOOP", "reasoning": "The two memories are duplicates."}'

	pipeline = ConsolidationPipeline(
		threshold=0.82,
		encoder=lambda _: np.array([1.0, 0.0], dtype=np.float32),
		completion_func=fake_completion,
		json_parser=lambda raw: {"decision": "NOOP", "reasoning": "The two memories are duplicates."},
	)
	existing = [_memory("User prefers email.", np.array([1.0, 0.0], dtype=np.float32))]
	new_memory = {"content": "User prefers email communication."}

	result = asyncio.run(pipeline.run(new_memory, existing))

	assert result.decision == ConsolidationDecision.NOOP
	assert result.llm_called is True
	assert result.existing_memory_id == existing[0].id


def test_consolidation_invalid_llm_output_falls_back_to_add():
	async def fake_completion(prompt: str, temperature: float) -> str:
		return "not-json"

	pipeline = ConsolidationPipeline(
		threshold=0.82,
		encoder=lambda _: np.array([1.0, 0.0], dtype=np.float32),
		completion_func=fake_completion,
		json_parser=lambda raw: {"decision": "UNKNOWN", "reasoning": "invalid"},
	)
	existing = [_memory("User lives in Delhi.", np.array([1.0, 0.0], dtype=np.float32), memory_type="fact")]
	new_memory = {"content": "User now lives in Mumbai."}

	result = asyncio.run(pipeline.run(new_memory, existing))

	assert result.decision == ConsolidationDecision.ADD
	assert result.llm_called is True
