from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse
from typing import Optional
import os

from engines.voice_engine import VoiceEngine
from utils.logger import get_logger

logger = get_logger("api.voice")
router = APIRouter()


@router.post("/voice")
async def voice_endpoint(
    audio: UploadFile = File(None),
    text: Optional[str] = Form(None),
    mode: str = Form("stt"),  # stt or tts
):
    """
    Voice endpoint:
    - mode=stt: audio upload -> transcript
    - mode=tts: text -> audio file (placeholder)
    """
    engine = VoiceEngine()

    if mode == "stt" and audio:
        contents = await audio.read()
        result = await engine.transcribe(contents, filename=audio.filename)
        result["version"] = os.getenv("APP_VERSION", "3.0.0")
        return JSONResponse(content=result)

    if mode == "tts" and text:
        result = await engine.synthesize(text)
        result["version"] = os.getenv("APP_VERSION", "3.0.0")
        return JSONResponse(content=result)

    return JSONResponse(
        status_code=400,
        content={"success": False, "error": "Invalid voice request. Provide audio (stt) or text (tts)."}
    )
