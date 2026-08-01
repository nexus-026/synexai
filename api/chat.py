"""
Main chat API — mirrors testa13.php behavior exactly.
POST /chat  (JSON body: {message, type?, session_id?})
POST /chat with file upload (multipart: file + message/context)
GET /memory?session_id=xxx
GET /history?session_id=xxx
POST /feedback
"""
import os
import re
import uuid
from typing import Optional

from fastapi import APIRouter, Request, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.ai_engine import process_message
from database.database import get_db
from utils.helpers import detect_comparison, extract_topic
from utils.logger import get_logger
from engines.file_engine import FileEngine

logger = get_logger("api.chat")
router = APIRouter()

MAX_MESSAGE_LENGTH = int(os.getenv("MAX_MESSAGE_LENGTH", "6000"))
APP_VERSION = os.getenv("APP_VERSION", "3.0.0")


class ChatRequest(BaseModel):
    message: str
    type: Optional[str] = None
    session_id: Optional[str] = None
    context: Optional[dict] = None


# In-memory session context (mirrors PHP $_SESSION behavior)
_session_contexts: dict = {}


@router.post("/chat")
async def chat_endpoint(
    request: Request,
    payload: ChatRequest | None = None,
    file: UploadFile = File(None),
    message: str = Form(""),
    context: str = Form(""),
    db=Depends(get_db),
):
    """
    Unified endpoint handling both JSON chat and file uploads.
    Mirrors testa13.php exactly.
    """
    is_file_upload = file is not None and file.filename

    if is_file_upload:
        # File analysis path (mirrors testa13 file upload)
        user_context = context.strip() or message.strip()
        if len(user_context) > MAX_MESSAGE_LENGTH:
            user_context = user_context[:MAX_MESSAGE_LENGTH]

        file_engine = FileEngine()
        contents = await file.read()
        result = await file_engine.analyze(
            message=user_context,
            file_bytes=contents,
            filename=file.filename,
        )
        result["version"] = APP_VERSION
        return JSONResponse(content=result)

    # JSON chat path
    if payload is None or not payload.message:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "Invalid or empty message payload."},
        )

    msg = payload.message.strip()
    if len(msg) > MAX_MESSAGE_LENGTH:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": f"Message too long (max {MAX_MESSAGE_LENGTH} characters)."},
        )

    session_id = payload.session_id or str(uuid.uuid4())[:16]

    # Session context (like PHP $_SESSION['nxsai_context'])
    if session_id not in _session_contexts:
        _session_contexts[session_id] = {
            "topic": "",
            "last_intent": "",
            "history": [],
            "turn": 0,
        }
    chat_ctx = _session_contexts[session_id]

    # Detect comparison
    comparison = detect_comparison(msg)

    # Detect SVG request
    svg_request = bool(re.search(
        r'\b(diagram|visualize|flowchart|draw|show me how|explain with (a )?diagram|cycle|process|steps)\b',
        msg, re.I
    ))

    # Process via AI Engine
    result = await process_message(
        message=msg,
        session_id=session_id,
        context=payload.context,
        comparison=comparison,
        svg_request=svg_request,
    )

    # Update session context (exactly like testa13.php)
    chat_ctx["topic"] = extract_topic(msg)
    chat_ctx["last_intent"] = result.get("intent", "chat")
    chat_ctx["history"].append({
        "q": msg,
        "intent": result.get("intent", "chat"),
        "time": __import__("time").time(),
    })
    chat_ctx["turn"] += 1
    if len(chat_ctx["history"]) > 10:
        chat_ctx["history"].pop(0)

    # Ensure response format matches frontend expectations
    response_payload = {
        "success": result.get("success", True),
        "type": result.get("type", "chat"),
        "response": result.get("response", ""),
        "sources": result.get("sources", []),
        "images": result.get("images", []),
        "svg": result.get("svg"),
        "intent": result.get("intent"),
        "confidence": result.get("confidence"),
        "search_used": result.get("search_used", False),
        "crawl_used": result.get("crawl_used", False),
        "context_count": result.get("context_count", 0),
        "version": APP_VERSION,
        "session_id": session_id,
    }

    return JSONResponse(content=response_payload)


@router.get("/memory")
async def get_memory(session_id: str):
    """Retrieve session memory/context."""
    ctx = _session_contexts.get(session_id, {
        "topic": "",
        "last_intent": "",
        "history": [],
        "turn": 0,
    })
    return JSONResponse(content={"success": True, "context": ctx, "version": APP_VERSION})


@router.get("/history")
async def get_history(session_id: str, limit: int = 20):
    """Retrieve conversation history for a session."""
    from sqlalchemy import select
    from database.database import async_session
    from database.models import Conversation, Message

    async with async_session() as db:
        conv_result = await db.execute(
            select(Conversation).where(Conversation.session_id == session_id)
        )
        conv = conv_result.scalars().first()
        if not conv:
            return JSONResponse(content={"success": True, "history": [], "version": APP_VERSION})

        msg_result = await db.execute(
            select(Message).where(Message.conversation_id == conv.id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        messages = msg_result.scalars().all()
        history = [
            {
                "role": m.role,
                "content": m.content,
                "intent": m.intent,
                "sources": m.sources,
                "images": m.images,
                "svg": m.svg,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in reversed(messages)
        ]
    return JSONResponse(content={"success": True, "history": history, "version": APP_VERSION})


class FeedbackRequest(BaseModel):
    message_id: int
    rating: int  # 1-5
    comment: Optional[str] = ""
    user_id: Optional[int] = None


@router.post("/feedback")
async def feedback_endpoint(payload: FeedbackRequest):
    """Log user feedback for learning."""
    from core.learning_engine import LearningEngine
    engine = LearningEngine()
    await engine.log_feedback(payload.user_id, payload.message_id, payload.rating, payload.comment)
    return JSONResponse(content={"success": True, "message": "Feedback recorded.", "version": APP_VERSION})
