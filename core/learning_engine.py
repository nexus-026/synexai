from typing import Optional, Dict, Any
from database.database import async_session
from database.models import LearningLog
from utils.logger import get_logger

logger = get_logger("learning_engine")


class LearningEngine:
    async def log_interaction(self, user_id: Optional[int], message: str, intent: str, result: Dict[str, Any]):
        async with async_session() as db:
            log = LearningLog(
                user_id=user_id,
                event_type="interaction",
                content=message[:2000],
                metadata={"intent": intent, "response_length": len(result.get("response", ""))},
            )
            db.add(log)
            await db.commit()

    async def log_feedback(self, user_id: Optional[int], message_id: int, rating: int, comment: str = ""):
        async with async_session() as db:
            log = LearningLog(
                user_id=user_id,
                event_type="feedback",
                content=comment,
                metadata={"message_id": message_id, "rating": rating},
            )
            db.add(log)
            await db.commit()

    async def log_correction(self, user_id: Optional[int], original: str, corrected: str):
        async with async_session() as db:
            log = LearningLog(
                user_id=user_id,
                event_type="correction",
                content=f"Original: {original}\nCorrected: {corrected}",
                metadata={},
            )
            db.add(log)
            await db.commit()
