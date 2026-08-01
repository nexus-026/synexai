from typing import Optional, Dict, Any
from sqlalchemy import select
from database.database import async_session
from database.models import User, MemoryEntry
from utils.logger import get_logger

logger = get_logger("user_context")


class UserContext:
    async def get_profile(self, user_id: int) -> Optional[Dict[str, Any]]:
        async with async_session() as db:
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalars().first()
            if not user:
                return None
            return {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "is_active": user.is_active,
                "is_admin": user.is_admin,
                "created_at": user.created_at.isoformat() if user.created_at else None,
            }

    async def get_preferences(self, user_id: int) -> Dict[str, Any]:
        async with async_session() as db:
            result = await db.execute(
                select(MemoryEntry).where(MemoryEntry.user_id == user_id, MemoryEntry.key.startswith("pref_"))
            )
            prefs = result.scalars().all()
            return {p.key.replace("pref_", ""): p.value for p in prefs}

    async def set_preference(self, user_id: int, key: str, value: str):
        async with async_session() as db:
            full_key = f"pref_{key}"
            result = await db.execute(
                select(MemoryEntry).where(MemoryEntry.user_id == user_id, MemoryEntry.key == full_key)
            )
            entry = result.scalars().first()
            if entry:
                entry.value = value
            else:
                db.add(MemoryEntry(user_id=user_id, key=full_key, value=value, topic="preference"))
            await db.commit()
