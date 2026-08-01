from typing import Optional, Dict, Any, List
from sqlalchemy import select
from database.database import async_session
from database.models import MemoryEntry
from utils.logger import get_logger

logger = get_logger("conversation_memory")


class ConversationMemory:
    async def get(self, session_id: str, key: str) -> Optional[str]:
        async with async_session() as db:
            result = await db.execute(
                select(MemoryEntry).where(MemoryEntry.session_id == session_id, MemoryEntry.key == key)
            )
            entry = result.scalars().first()
            return entry.value if entry else None

    async def set(self, session_id: str, key: str, value: str, topic: str = "", confidence: float = 1.0):
        async with async_session() as db:
            result = await db.execute(
                select(MemoryEntry).where(MemoryEntry.session_id == session_id, MemoryEntry.key == key)
            )
            entry = result.scalars().first()
            if entry:
                entry.value = value
                entry.topic = topic or entry.topic
                entry.confidence = confidence
            else:
                db.add(MemoryEntry(session_id=session_id, key=key, value=value, topic=topic, confidence=confidence))
            await db.commit()

    async def get_history(self, session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        async with async_session() as db:
            result = await db.execute(
                select(MemoryEntry).where(MemoryEntry.session_id == session_id).order_by(MemoryEntry.created_at.desc()).limit(limit)
            )
            return [{"key": e.key, "value": e.value, "topic": e.topic, "confidence": e.confidence} for e in result.scalars().all()]
