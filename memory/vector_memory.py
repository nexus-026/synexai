import json
import math
from typing import List, Dict, Any, Optional
from database.database import async_session
from database.models import KnowledgeEntry
from utils.helpers import cosine_similarity, extract_keywords
from utils.logger import get_logger

logger = get_logger("vector_memory")


class VectorMemory:
    """
    Lightweight vector memory using JSON-stored embeddings.
    In production, replace with pgvector or a dedicated vector DB.
    """

    async def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        # Keyword-based fallback when embeddings aren't available
        keywords = extract_keywords(query, 5)
        async with async_session() as db:
            from sqlalchemy import select
            result = await db.execute(select(KnowledgeEntry))
            entries = result.scalars().all()
            scored = []
            for entry in entries:
                score = 0
                text = (entry.topic + " " + entry.content).lower()
                for kw in keywords:
                    score += text.count(kw)
                # If embeddings exist, boost with cosine similarity
                if entry.embedding and isinstance(entry.embedding, list):
                    # We would need the query embedding to compare properly.
                    # For now, skip numerical comparison without an embedding model.
                    pass
                if score > 0:
                    scored.append((score, entry))
            scored.sort(reverse=True, key=lambda x: x[0])
            return [{"topic": e.topic, "content": e.content, "source": e.source, "score": s} for s, e in scored[:top_k]]

    async def store(self, topic: str, content: str, source: str = "auto", embedding: Optional[List[float]] = None):
        async with async_session() as db:
            entry = KnowledgeEntry(
                topic=topic[:255],
                content=content[:4000],
                source=source,
                embedding=embedding,
            )
            db.add(entry)
            await db.commit()
