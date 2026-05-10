from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Ollama
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "gemma2:4b-instruct-q4_K_M"
    OLLAMA_TIMEOUT_SECONDS: int = 60

    # Embeddings
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    EMBEDDING_DIMENSION: int = 384

    # Consolidation
    CONSOLIDATION_THRESHOLD: float = 0.82
    MIN_CONFIDENCE: float = 0.5

    # Database
    DATABASE_PATH: str = "./memories.db"

    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    class Config:
        env_file = ".env"

# Initialize global settings
settings = Settings()
