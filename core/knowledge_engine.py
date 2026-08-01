import json
from typing import Optional, List
from sqlalchemy import select, func
from database.database import async_session
from database.models import KnowledgeEntry
from utils.helpers import extract_keywords, cosine_similarity
from utils.logger import get_logger

logger = get_logger("knowledge_engine")


class KnowledgeEngine:
    async def search(self, query: str, top_k: int = 3) -> Optional[str]:
        keywords = extract_keywords(query, 5)
        async with async_session() as db:
            # Simple keyword search first
            result = await db.execute(select(KnowledgeEntry))
            entries = result.scalars().all()
            scored = []
            for entry in entries:
                score = 0
                entry_text = (entry.topic + " " + entry.content).lower()
                for kw in keywords:
                    if kw in entry_text:
                        score += entry.content.lower().count(kw)
                if entry.embedding:
                    # If we have embeddings, use cosine similarity
                    # For now, placeholder since we don't compute embeddings on the fly without sentence-transformers
                    pass
                score += entry.score
                if score > 0:
                    scored.append((score, entry))
            scored.sort(reverse=True, key=lambda x: x[0])
            if scored:
                return "\n\n".join([e.content for _, e in scored[:top_k]])
        return None

    async def store_if_useful(self, query: str, response: str, intent: str):
        # Store only factual/research responses as knowledge
        if intent not in ("research", "education", "weather", "country", "dictionary"):
            return
        topic = " ".join(extract_keywords(query + " " + response, 5))
        if not topic:
            return
        async with async_session() as db:
            entry = KnowledgeEntry(topic=topic[:255], content=response[:4000], source="conversation")
            db.add(entry)
            await db.commit()
            logger.info(f"Stored knowledge entry: {topic[:50]}")

    async def add_knowledge(self, topic: str, content: str, source: str = "manual"):
        async with async_session() as db:
            entry = KnowledgeEntry(topic=topic, content=content, source=source)
            db.add(entry)
            await db.commit()

    async def get_all(self, limit: int = 100) -> List[KnowledgeEntry]:
        async with async_session() as db:
            result = await db.execute(select(KnowledgeEntry).order_by(KnowledgeEntry.created_at.desc()).limit(limit))
            return result.scalars().all()
