import asyncio

from app.pipelines.extraction import ExtractionPipeline


def test_extraction_filters_invalid_and_low_confidence_items():
	async def fake_completion(prompt: str, temperature: float) -> str:
		return "ignored by fake parser"

	def fake_parser(raw: str):
		return [
			{
				"content": "User prefers concise responses.",
				"memory_type": "preference",
				"confidence": 0.92,
				"source": "user_stated",
			},
			{
				"content": "Low confidence should be dropped.",
				"memory_type": "fact",
				"confidence": 0.20,
				"source": "agent_inferred",
			},
			{
				"content": "",
				"memory_type": "fact",
				"confidence": 0.99,
				"source": "user_stated",
			},
			{"content": "Missing schema field", "memory_type": "fact", "confidence": 0.80},
		]

	pipeline = ExtractionPipeline(
		min_confidence=0.5,
		completion_func=fake_completion,
		json_parser=fake_parser,
	)
	result = asyncio.run(pipeline.run("test conversation"))

	assert len(result) == 1
	assert result[0].content == "User prefers concise responses."
	assert result[0].memory_type == "preference"


def test_extraction_returns_empty_when_parser_fails():
	async def fake_completion(prompt: str, temperature: float) -> str:
		return "bad-json"

	def broken_parser(raw: str):
		raise ValueError("cannot parse")

	pipeline = ExtractionPipeline(
		completion_func=fake_completion,
		json_parser=broken_parser,
	)
	result = asyncio.run(pipeline.run("another conversation"))

	assert result == []
