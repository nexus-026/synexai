import os
from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from engines.image_engine import ImageEngine
from utils.logger import get_logger

logger = get_logger("api.images")
router = APIRouter()


class ImageRequest(BaseModel):
    prompt: str
    model: Optional[str] = None
    width: Optional[int] = 1024
    height: Optional[int] = 1024


@router.post("/generate-image")
async def generate_image(
    prompt: str = Form(...),
    model: Optional[str] = Form(None),
):
    """Generate image via Pollinations AI — compatible with frontend image requests."""
    engine = ImageEngine()
    result = await engine.generate(prompt)
    result["version"] = os.getenv("APP_VERSION", "3.0.0")
    return JSONResponse(content=result)


@router.get("/gallery")
async def gallery(limit: int = 20):
    """List recently generated images."""
    import glob
    files = sorted(glob.glob("generated/*"), key=os.path.getmtime, reverse=True)[:limit]
    images = []
    for f in files:
        images.append({
            "filename": os.path.basename(f),
            "url": f"/generated/{os.path.basename(f)}",
            "size": os.path.getsize(f),
        })
    return JSONResponse(content={"success": True, "images": images, "count": len(images)})
