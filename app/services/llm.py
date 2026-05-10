import httpx
import json
import re
from typing import Union, List, Dict, Any
from app.core.config import settings
from app.core.logger import logger

async def generate_completion(prompt: str, temperature: float = 0.1) -> str:
    """
    Calls the local Ollama instance.
    FRS §8.3: Explictly NO automatic retries. Bubbles up Timeout or Error immediately.
    """
    url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    payload = {
        "model": settings.OLLAMA_MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "options": {
            "temperature": temperature
        },
        "stream": False
    }

    async with httpx.AsyncClient(timeout=settings.OLLAMA_TIMEOUT_SECONDS) as client:
        # This will raise HTTPStatusError or RequestError/TimeoutException natively 
        # which satisfies the no-retry fail-fast requirement
        response = await client.post(url, json=payload)
        
        if response.status_code >= 400:
            logger.error(f"Ollama Error [{response.status_code}]: {response.text} - Payload: {payload}")
            
        response.raise_for_status()
        
        data = response.json()
        return data.get("message", {}).get("content", "")

# def clean_llm_json(raw: str) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
#     """
#     Strips markdown code fences (```json ... ```) and parses the strict inner JSON.
#     FRS §6.1 Requirement for Gemma 4B's extraneous outputs.
#     """
#     # Attempt to find the first JSON array or object
#     # Often models prefix with text like "Here is the output: ```json\n[{...}]\n```"
#     match = re.search(r'(\[.*\]|\{.*\})', raw, re.DOTALL)
#     if not match:
#          # Fallback to general parsing if no brackets matched but it could be valid JSON
#          cleaned = raw
#     else:
#          cleaned = match.group(1)
         
#     # Remove standard markdown code fences that might be trapped within or around
#     cleaned = re.sub(r'```(?:json)?|```', '', cleaned).strip()
    
#     try:
#         return json.loads(cleaned)
#     except json.JSONDecodeError as e:
#         logger.error(f"Failed to parse LLM JSON output: {e.msg}\nRaw Output: {raw}\nCleaned: {cleaned}")
#         raise ValueError("Invalid JSON output strictly required from LLM.") from e
    
def clean_llm_json(raw: str) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    # Find ALL matches and take the last one — Llama reasons before outputting
    matches = list(re.finditer(r'(\[.*?\]|\{.*?\})', raw, re.DOTALL))
    if not matches:
        raise ValueError("No JSON object found in LLM output.")
    cleaned = matches[-1].group(1)
    cleaned = re.sub(r'```(?:json)?|```', '', cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error(
            "Failed to parse LLM JSON",
            error=str(e),
            raw=raw,
            cleaned=cleaned
        )
        raise ValueError("Invalid JSON from LLM.") from e
