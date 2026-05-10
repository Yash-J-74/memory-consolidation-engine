from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

import numpy as np

from app.core.config import settings
from app.core.logger import logger
from app.db.models import Memory
from app.pipelines.extraction import ExtractedMemory
from app.services.llm import clean_llm_json, generate_completion


# CLASSIFICATION_PROMPT = """You are an AI memory manager.
# Your task is to classify the relationship between an EXISTING memory and a NEW memory.

# Analyze the memories and choose ONE of the following precise actions:

# - NOOP: The new memory is identical or a subset. (e.g., "I live in Austin" vs "I reside in Austin"). Discard the new one.
# - ADD: The new memory presents entirely separate conditions or additional orthogonal info. (e.g., "I prefer email" vs "I prefer phone for emergencies"). Keep both.
# - UPDATE: The new memory implies a chronological change or outright SUPERSEDES the old fact. (e.g., "I live in Austin" vs "I moved to Seattle", or "I use React" vs "I switched to SvelteKit"). The old one is outdated.
# - CONFLICT: They directly contradict with NO temporal change or conditions. (e.g., "My favorite color is blue" vs "My favorite color is red").

# IMPORTANT: Re-read the definition of UPDATE. If a person "moved to" a new city, or "switched" to a new tool, or "uses" a different exclusive framework now, it is ALWAYS an UPDATE.

# Output ONLY valid JSON matching this schema:
# {{"decision": "<NOOP|ADD|UPDATE|CONFLICT>", "reasoning": "<short explanation>"}}

# EXAMPLE 1:
# EXISTING: "User lives in Austin"
# NEW: "User moved to Seattle"
# OUTPUT: {{"decision": "UPDATE", "reasoning": "Location has chronologically updated to Seattle."}}

# EXAMPLE 2:
# EXISTING: "User uses React"
# NEW: "User uses SvelteKit"
# OUTPUT: {{"decision": "UPDATE", "reasoning": "Framework replaced with SvelteKit."}}

# EXAMPLE 3:
# EXISTING: "User prefers email"
# NEW: "User likes phone calls for emergencies"
# OUTPUT: {{"decision": "ADD", "reasoning": "Separate specific condition introduced."}}

# NOW CLASSIFY:
# EXISTING: "{existing}"
# NEW: "{new}"
# OUTPUT:"""

CLASSIFICATION_PROMPT = """You are a memory consolidation classifier.
Given an EXISTING memory and a NEW memory, output exactly one decision.

DECISION DEFINITIONS:
- NOOP: New memory means the same thing as existing. Discard new. (rewordings, paraphrases, subsets)
- ADD: New memory is about a genuinely different thing. Keep both. (different topic, different condition, orthogonal fact)
- UPDATE: New memory explicitly supersedes existing due to a real-world change. Replace existing. (moved cities, switched tools, changed role)
- CONFLICT: New memory contradicts existing with no evidence of change. Flag both. (same topic, opposite claim, no "moved/switched/now" language)

RULE — UPDATE requires explicit change language: words like "moved", "switched", "now uses", "changed to", "no longer". Absence of change language means CONFLICT, not UPDATE.

EXAMPLES:

EXISTING: "User lives in Austin"
NEW: "User moved to Seattle"
OUTPUT: {{"decision": "UPDATE", "reasoning": "Explicit move — location changed."}}

EXISTING: "User uses React"
NEW: "User uses SvelteKit"
OUTPUT: {{"decision": "CONFLICT", "reasoning": "No change language. Could be a second project or a contradiction."}}

EXISTING: "User uses React"
NEW: "User switched to SvelteKit"
OUTPUT: {{"decision": "UPDATE", "reasoning": "Explicit switch — framework replaced."}}

EXISTING: "User prefers email"
NEW: "User prefers email for all communication"
OUTPUT: {{"decision": "NOOP", "reasoning": "New memory is a restatement of the existing one."}}

EXISTING: "User prefers email"
NEW: "User prefers phone for urgent issues"
OUTPUT: {{"decision": "ADD", "reasoning": "Conditional preference on a different channel — orthogonal."}}

EXISTING: "User prefers email"
NEW: "User prefers phone"
OUTPUT: {{"decision": "CONFLICT", "reasoning": "Same domain, opposite preference, no change language."}}

NOW CLASSIFY:
EXISTING: "{existing}"
NEW: "{new}"
OUTPUT:"""


class ConsolidationDecision(str, Enum):
	ADD = "ADD"
	NOOP = "NOOP"
	UPDATE = "UPDATE"
	CONFLICT = "CONFLICT"


@dataclass
class ConsolidationResult:
	decision: ConsolidationDecision
	reasoning: str
	llm_called: bool
	similarity_score: Optional[float] = None
	existing_memory_id: Optional[str] = None
	embedding: Optional[np.ndarray] = None


class ConsolidationPipeline:
	def __init__(
		self,
		threshold: Optional[float] = None,
		temperature: float = 0.0,
		encoder: Optional[Callable[[str], np.ndarray]] = None,
		completion_func: Optional[Callable[[str, float], Awaitable[str]]] = None,
		json_parser: Optional[Callable[[str], Any]] = None,
	) -> None:
		self._threshold = settings.CONSOLIDATION_THRESHOLD if threshold is None else threshold
		self._temperature = temperature
		self._encoder = encoder
		self._completion = completion_func or generate_completion
		self._json_parser = json_parser or clean_llm_json

	async def run(
		self,
		new_memory: Union[ExtractedMemory, Dict[str, Any]],
		existing_memories: List[Memory],
		threshold: Optional[float] = None
	) -> ConsolidationResult:
		new_content = self._extract_content(new_memory)
		if not new_content:
			return ConsolidationResult(
				decision=ConsolidationDecision.ADD,
				reasoning="Missing new memory content; defaulting to ADD.",
				llm_called=False,
			)

		encode_fn = self._resolve_encoder()
		new_embedding = encode_fn(new_content)
		new_embedding = self._coerce_embedding(new_embedding)

		if not existing_memories:
			return ConsolidationResult(
				decision=ConsolidationDecision.ADD,
				reasoning="No existing memories for this memory_type.",
				llm_called=False,
				embedding=new_embedding
			)

		best_memory: Optional[Memory] = None
		best_score = float("-inf")

		for memory in existing_memories:
			if memory.embedding is None:
				continue
			try:
				mem_emb = self._coerce_embedding(memory.embedding)
				score = float(np.dot(new_embedding, mem_emb))
			except Exception as exc:
				logger.error(
					"Embedding similarity computation failed",
					error=str(exc),
					new_embedding_meta=self._embedding_meta(new_embedding),
					raw_memory_embedding_meta=self._embedding_meta(memory.embedding),
					coerced_memory_embedding_meta=self._embedding_meta(mem_emb if 'mem_emb' in locals() else None),
					memory_id=memory.id,
					memory_content=memory.content,
				)
				raise
			if score > best_score:
				best_score = score
				best_memory = memory

		if best_memory is None:
			logger.info("No comparable embeddings found", new_content=new_content)
			return ConsolidationResult(
				decision=ConsolidationDecision.ADD,
				reasoning="No comparable embeddings found; defaulting to ADD.",
				llm_called=False,
				embedding=new_embedding,
			)

		eval_threshold = threshold if threshold is not None else self._threshold
		logger.info(
			"Similarity score calculated",
			new_content=new_content,
			best_match_id=best_memory.id,
			best_match_content=best_memory.content,
			similarity_score=best_score,
			threshold=eval_threshold
		)
		if best_score < eval_threshold:
			return ConsolidationResult(
				decision=ConsolidationDecision.ADD,
				reasoning="Similarity below consolidation threshold.",
				llm_called=False,
				similarity_score=best_score,
				existing_memory_id=best_memory.id,
				embedding=new_embedding,
			)

		prompt = CLASSIFICATION_PROMPT.format(existing=best_memory.content, new=new_content)
		try:
			raw = await self._completion(prompt, self._temperature)
			parsed = self._json_parser(raw)
			decision, reasoning = self._parse_llm_classification(parsed)
			return ConsolidationResult(
				decision=decision,
				reasoning=reasoning,
				llm_called=True,
				similarity_score=best_score,
				existing_memory_id=best_memory.id,
				embedding=new_embedding,
			)
		except Exception:
			return ConsolidationResult(
				decision=ConsolidationDecision.ADD,
				reasoning="LLM classification failed; defaulting safely to ADD.",
				llm_called=True,
				similarity_score=best_score,
				existing_memory_id=best_memory.id,
				embedding=new_embedding,
			)

	def _resolve_encoder(self) -> Callable[[str], np.ndarray]:
		if self._encoder is not None:
			return self._encoder

		# Lazy import avoids loading heavy model at module import time.
		from app.services.embedder import encode

		return encode

	def _extract_content(self, new_memory: Union[ExtractedMemory, Dict[str, Any]]) -> str:
		if isinstance(new_memory, ExtractedMemory):
			return new_memory.content
		if isinstance(new_memory, dict):
			return str(new_memory.get("content", "")).strip()
		return ""

	def _coerce_embedding(self, embedding: Any) -> np.ndarray:
		if isinstance(embedding, np.ndarray):
			if embedding.dtype != np.float32:
				return embedding.astype(np.float32)
			return embedding
		if isinstance(embedding, (bytes, bytearray, memoryview)):
			return np.frombuffer(bytes(embedding), dtype=np.float32)
		return np.asarray(embedding, dtype=np.float32)

	def _embedding_meta(self, embedding: Any) -> Dict[str, Any]:
		if embedding is None:
			return {"type": "None"}

		meta: Dict[str, Any] = {"type": str(type(embedding))}
		if isinstance(embedding, np.ndarray):
			meta.update(
				{
					"dtype": str(embedding.dtype),
					"shape": tuple(int(x) for x in embedding.shape),
					"kind": embedding.dtype.kind,
					"itemsize": int(embedding.dtype.itemsize),
				}
			)
			preview_count = min(3, int(embedding.size))
			if preview_count > 0:
				meta["preview"] = [str(embedding.flat[i]) for i in range(preview_count)]
		elif isinstance(embedding, (bytes, bytearray, memoryview)):
			meta["length"] = len(bytes(embedding))
		else:
			meta["repr"] = repr(embedding)[:200]
		return meta

	def _parse_llm_classification(self, parsed: Any) -> tuple[ConsolidationDecision, str]:
		if not isinstance(parsed, dict):
			raise ValueError("Classification output must be a JSON object")

		raw_decision = str(parsed.get("decision", "")).strip().upper()
		if raw_decision not in {d.value for d in ConsolidationDecision}:
			raise ValueError("Unsupported consolidation decision")

		reasoning = str(parsed.get("reasoning", "")).strip() or "No reasoning provided."
		return ConsolidationDecision(raw_decision), reasoning
