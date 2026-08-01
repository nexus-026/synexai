import os
import random
from typing import Dict, Any
import httpx

from utils.logger import get_logger

logger = get_logger("image_engine")

POLLINATIONS_IMAGE_URL = os.getenv("POLLINATIONS_IMAGE_URL", "https://image.pollinations.ai/prompt/")
POLLINATIONS_MODEL = os.getenv("POLLINATIONS_MODEL", "flux")
IMAGE_MAX_RETRIES = int(os.getenv("IMAGE_MAX_RETRIES", "3"))
IMAGE_TIMEOUT = int(os.getenv("IMAGE_TIMEOUT", "30"))


class ImageEngine:
    async def generate(self, prompt: str) -> Dict[str, Any]:
        # Clean prompt
        clean = re.sub(r'^(generate|create|make|draw|design|render)\s+(an?\s+)?(image|picture|photo|logo|art|wallpaper|avatar)\s+(of\s+)?', '', prompt, flags=re.I)
        clean = clean.strip()[:400] or prompt.strip()[:400]
        enhanced = f"{clean}, high quality, detailed, professional"

        seed = random.randint(1000, 999999)
        url = f"{POLLINATIONS_IMAGE_URL}{httpx.URL.encode(enhanced)}?model={POLLINATIONS_MODEL}&nologo=true&seed={seed}&width=1024&height=1024"

        # Try to download and cache
        cached_url = None
        for attempt in range(1, IMAGE_MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=IMAGE_TIMEOUT, follow_redirects=True) as client:
                    r = await client.get(url)
                    if r.status_code == 200 and len(r.content) > 1000:
                        # Save to generated/
                        os.makedirs("generated", exist_ok=True)
                        ext = "jpg"
                        ct = r.headers.get("content-type", "")
                        if "png" in ct:
                            ext = "png"
                        elif "gif" in ct:
                            ext = "gif"
                        elif "webp" in ct:
                            ext = "webp"
                        filename = f"img_{seed}_{random.randint(1000,9999)}.{ext}"
                        path = os.path.join("generated", filename)
                        with open(path, "wb") as f:
                            f.write(r.content)
                        cached_url = f"/generated/{filename}"
                        break
            except Exception as e:
                logger.warning(f"Image download attempt {attempt} failed: {e}")

        final_url = cached_url or url

        return {
            "success": True,
            "type": "image",
            "response": f'Here is your generated image based on: *"{clean}"*',
            "image": {
                "url": final_url,
                "original": clean,
                "enhanced": enhanced,
                "cached": cached_url is not None,
            },
            "sources": [],
        }


import re
