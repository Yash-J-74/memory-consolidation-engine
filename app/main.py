from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from contextlib import asynccontextmanager

from app.api import health, sessions, memories, admin
from app.db.database import init_db, get_db_connection
from app.core.logger import logger

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize the database on startup
    conn = get_db_connection()
    try:
        init_db(conn)
    finally:
        conn.close()
    yield

app = FastAPI(title="Memory Consolidation Engine POC", lifespan=lifespan)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for this POC
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Exception Handlers
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    detail = exc.detail
    logger.warning(
        "HTTP exception raised",
        method=request.method,
        path=request.url.path,
        status_code=exc.status_code,
        detail=detail,
    )
    if isinstance(detail, str):
        return JSONResponse(status_code=exc.status_code, content={"error": detail, "detail": {}})
    return JSONResponse(status_code=exc.status_code, content={"error": "HTTP Exception", "detail": detail})

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(
        "Request validation failed",
        method=request.method,
        path=request.url.path,
        errors=exc.errors(),
    )
    return JSONResponse(
        status_code=422,
        content={"error": "Validation Error", "detail": {"errors": exc.errors()}}
    )

@app.exception_handler(Exception)
async def exception_handler(request: Request, exc: Exception):
    logger.exception(
        "Unhandled server error",
        method=request.method,
        path=request.url.path,
    )
    return JSONResponse(
        status_code=500,
        content={"error": "Internal Server Error", "detail": {"message": str(exc)}}
    )

# Include Routers
app.include_router(health.router)
app.include_router(sessions.router)
app.include_router(memories.router)
app.include_router(admin.router)

if __name__ == "__main__":
    # Run with `python -m app.main` to enable auto-reload on changes within the "app" directory
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_dirs=["app"],
    )
