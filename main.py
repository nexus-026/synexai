import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api import chat, users, images, files, voice
from database.database import engine, Base
from utils.logger import get_logger

logger = get_logger("main")
APP_VERSION = os.getenv("APP_VERSION", "3.0.0")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("NXS AI backend starting up...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Shutdown
    await engine.dispose()
    logger.info("NXS AI backend shut down.")


app = FastAPI(
    title="NXS AI Backend",
    version=APP_VERSION,
    docs_url="/docs" if os.getenv("DEBUG") else None,
    redoc_url="/redoc" if os.getenv("DEBUG") else None,
    lifespan=lifespan,
)

# CORS — allow InfinityFree frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Internal server error",
            "version": APP_VERSION,
        },
    )


# Include routers
app.include_router(chat.router, prefix="", tags=["Chat"])
app.include_router(users.router, prefix="/auth", tags=["Auth"])
app.include_router(images.router, prefix="", tags=["Images"])
app.include_router(files.router, prefix="", tags=["Files"])
app.include_router(voice.router, prefix="", tags=["Voice"])


@app.get("/health")
async def health():
    return {"status": "ok", "version": APP_VERSION}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "10000")),
    )
