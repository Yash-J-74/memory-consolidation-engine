import os

# Default to the backend URL typical for local dev
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
