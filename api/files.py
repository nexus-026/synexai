import os
import shutil
from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import JSONResponse
from typing import Optional

from engines.file_engine import FileEngine
from utils.logger import get_logger

logger = get_logger("api.files")
router = APIRouter()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/analyze-file")
async def analyze_file(
    file: UploadFile = File(...),
    context: Optional[str] = Form(""),
    message: Optional[str] = Form(""),
):
    """
    Analyze uploaded file — mirrors testa13.php file upload behavior.
    Accepts: PDF, DOCX, TXT, CSV, XLSX, images, code files.
    """
    user_context = context.strip() or message.strip()

    # Save file
    safe_name = os.path.basename(file.filename or "upload")
    dest_path = os.path.join(UPLOAD_DIR, safe_name)
    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Analyze
    engine = FileEngine()
    contents = open(dest_path, "rb").read()
    result = await engine.analyze(
        message=user_context,
        file_path=dest_path,
        filename=safe_name,
    )
    result["version"] = os.getenv("APP_VERSION", "3.0.0")
    return JSONResponse(content=result)
