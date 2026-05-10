from fastapi import APIRouter, Depends, HTTPException
import sqlite3
import httpx
from app.db.database import get_db
from app.core.config import settings

router = APIRouter(prefix="/api/v1", tags=["health"])

@router.get("/health")
async def health_check(db: sqlite3.Connection = Depends(get_db)):
    """Health check for all system dependencies."""
    status = "ok"
    details = {"components": {}}

    # Check DB
    try:
        db.execute("SELECT 1")
        details["components"]["db"] = "ok"
    except Exception as e:
        status = "degraded"
        details["components"]["db"] = f"failed: {str(e)}"

    # Check Ollama
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=5.0)
            if res.status_code == 200:
                details["components"]["ollama"] = "ok"
            else:
                status = "degraded"
                details["components"]["ollama"] = f"failed: http {res.status_code}"
    except Exception as e:
        status = "degraded"
        details["components"]["ollama"] = f"failed: {str(e)}"

    details["db_path"] = settings.DATABASE_PATH

    response_body = {"status": status, **details}

    if status == "degraded":
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content=response_body)

    return response_body
