from typing import Optional, Dict, Any
from sqlalchemy import select
from database.database import async_session
from database.models import Conversation, Message
from utils.logger import get_logger

logger = get_logger("conversation_engine")


class ConversationEngine:
    async def get_context(self, session_id: str) -> Optional[Dict[str, Any]]:
        async with async_session() as db:
            result = await db.execute(
                select(Conversation).where(Conversation.session_id == session_id).order_by(Conversation.created_at.desc())
            )
            conv = result.scalars().first()
            if not conv:
                return None
            # Get last few messages
            msg_result = await db.execute(
                select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at.desc()).limit(5)
            )
            messages = msg_result.scalars().all()
            return {
                "topic": conv.title or "",
                "intent": conv.intent or "",
                "history": [{"role": m.role, "content": m.content, "intent": m.intent} for m in reversed(messages)],
            }

    async def save_turn(self, session_id: str, user_msg: str, result: Dict, intent: str):
        async with async_session() as db:
            result_conv = await db.execute(
                select(Conversation).where(Conversation.session_id == session_id)
            )
            conv = result_conv.scalars().first()
            if not conv:
                conv = Conversation(session_id=session_id, title=user_msg[:80], intent=intent)
                db.add(conv)
                await db.flush()
            else:
                conv.intent = intent
            db.add(Message(
                conversation_id=conv.id,
                role="user",
                content=user_msg,
                intent=intent,
            ))
            db.add(Message(
                conversation_id=conv.id,
                role="assistant",
                content=result.get("response", ""),
                intent=intent,
                sources=result.get("sources"),
                images=result.get("images"),
                svg=result.get("svg"),
            ))
            await db.commit()
