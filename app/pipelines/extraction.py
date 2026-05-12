from dataclasses import dataclass
from typing import Any, Awaitable, Callable, List, Optional

from app.core.config import settings
from app.services.llm import clean_llm_json, generate_completion


EXTRACTION_PROMPT = """You are a memory extraction system for an AI assistant.
Extract discrete, persistent facts about the user from the conversation below.

RULES:
- Extract only information that would be useful to remember across future conversations
- Do NOT extract transient details (e.g. "user said hello")
- Do NOT extract historical transitions (e.g. avoid "user previously used React"). Extract only the absolute current state.
- Do NOT guess or extract implied opposites (e.g. if user states a preference for mornings, do not infer they are unavailable in the afternoons).
- Each memory must be a single, self-contained declarative statement
- Return ONLY a JSON array. No explanation, no markdown, no preamble.

SCHEMA (each item must have exactly these fields):
[
  {{
    "content": "<declarative statement about the user>",
    "memory_type": "<one of: preference | fact | event>",
    "confidence": <float between 0.0 and 1.0>,
    "source": "<one of: user_stated | agent_inferred>"
  }}
]

DEFINITIONS:
- preference: how the user wants to interact or be treated
- fact: objective information about the user (location, job, etc.)
- event: something that happened to or was done by the user
- user_stated: the user said this directly
- agent_inferred: this was implied but not said explicitly

CONVERSATION:
{conversation}

JSON ARRAY:"""


@dataclass
class ExtractedMemory:
	content: str
	memory_type: str
	confidence: float
	source: str


class ExtractionPipeline:
	def __init__(
		self,
		min_confidence: Optional[float] = None,
		temperature: float = 0.1,
		completion_func: Optional[Callable[[str, float], Awaitable[str]]] = None,
		json_parser: Optional[Callable[[str], Any]] = None,
	) -> None:
		self._min_confidence = settings.MIN_CONFIDENCE if min_confidence is None else min_confidence
		self._temperature = temperature
		self._completion = completion_func or generate_completion
		self._json_parser = json_parser or clean_llm_json

	async def run(self, conversation: str) -> List[ExtractedMemory]:
		prompt = EXTRACTION_PROMPT.format(conversation=conversation)
		raw = await self._completion(prompt, self._temperature)

		# Parse failures are dropped as empty extraction output.
		try:
			parsed = self._json_parser(raw)
		except Exception:
			return []

		if not isinstance(parsed, list):
			return []

		extracted: List[ExtractedMemory] = []
		for item in parsed:
			maybe = self._to_memory(item)
			if maybe is not None:
				extracted.append(maybe)

		return extracted

	def _to_memory(self, item: Any) -> Optional[ExtractedMemory]:
		if not isinstance(item, dict):
			return None

		required_keys = {"content", "memory_type", "confidence", "source"}
		if not required_keys.issubset(item.keys()):
			return None

		content = str(item["content"]).strip()
		memory_type = str(item["memory_type"]).strip()
		source = str(item["source"]).strip()
		try:
			confidence = float(item["confidence"])
		except (TypeError, ValueError):
			return None

		if not content:
			return None
		if memory_type not in {"preference", "fact", "event"}:
			return None
		if source not in {"user_stated", "agent_inferred"}:
			return None
		if confidence < self._min_confidence:
			return None

		return ExtractedMemory(
			content=content,
			memory_type=memory_type,
			confidence=confidence,
			source=source,
		)
