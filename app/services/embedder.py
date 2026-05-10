import numpy as np
import httpx
from sentence_transformers import SentenceTransformer
from app.core.config import settings

# Initialize model at startup
_model = SentenceTransformer(settings.EMBEDDING_MODEL)

def encode(text: str) -> np.ndarray:
    """
    Encodes unstructured text into a normalized dense vector representation.
    Normalizing guarantees that dot product matches cosine similarity.
    """
    # # encode() returns a numpy array or torch tensor based on arguments
    # # normalize_embeddings=True normalizes vectors to length 1
    embedding = _model.encode(text, normalize_embeddings=True)
    # 
    # # Ensure it's a normalized float32 numpy array
    return np.array(embedding, dtype=np.float32)

    # url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/embeddings"
    # payload = {
    #     "model": settings.EMBEDDING_MODEL,
    #     "prompt": text
    # }
    
    # with httpx.Client(timeout=settings.OLLAMA_TIMEOUT_SECONDS) as client:
    #     response = client.post(url, json=payload)
    #     response.raise_for_status()
    #     embedding = response.json().get("embedding", [])
        
    #     # Normalize the embedding to ensure dot product matches cosine similarity
    #     arr = np.array(embedding, dtype=np.float32)
    #     norm = np.linalg.norm(arr)
    #     if norm > 0:
    #         arr = arr / norm
    #     return arr
