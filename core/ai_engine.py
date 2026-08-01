from typing import Dict, Any, Optional
from core.intent_classifier import classify_intent
from core.reasoning_engine import ReasoningEngine
from core.conversation_engine import ConversationEngine
from core.knowledge_engine import KnowledgeEngine
from core.learning_engine import LearningEngine
from engines.research_engine import ResearchEngine
from engines.code_engine import CodeEngine
from engines.image_engine import ImageEngine
from engines.network_engine import NetworkEngine
from engines.file_engine import FileEngine
from utils.logger import get_logger

logger = get_logger("ai_engine")


class AIEngine:
    def __init__(self):
        self.reasoning = ReasoningEngine()
        self.conversation = ConversationEngine()
        self.knowledge = KnowledgeEngine()
        self.learning = LearningEngine()
        self.research = ResearchEngine()
        self.code = CodeEngine()
        self.image = ImageEngine()
        self.network = NetworkEngine()
        self.file = FileEngine()

    async def process(self, message: str, session_id: str, user_id: Optional[int] = None,
                      context: Optional[Dict] = None, comparison: Optional[Dict] = None,
                      svg_request: bool = False) -> Dict[str, Any]:
        """
        Main orchestration flow:
        Input -> Intent Classifier -> Reasoning -> Tool Selection -> Response -> Memory -> Knowledge
        """
        # 1. Intent Classification
        intent_result = classify_intent(message)
        intent = intent_result["intent"]

        # 2. Conversation context (follow-up detection)
        conv = await self.conversation.get_context(session_id)
        is_follow_up = False
        if conv and conv.get("topic"):
            from utils.helpers import detect_follow_up
            is_follow_up = detect_follow_up(message, conv["topic"])
            if is_follow_up and intent in ("research", "general"):
                message = f"{conv['topic']} {message}"

        # 3. Reasoning / Tool Selection
        tools_needed = self.reasoning.select_tools(intent, message)

        # 4. Execute
        result = await self._execute_tools(
            intent, message, tools_needed, comparison=comparison, svg_request=svg_request
        )

        # 5. Save memory & context
        await self.conversation.save_turn(session_id, message, result, intent)
        if result.get("response"):
            await self.knowledge.store_if_useful(message, result["response"], intent)

        # 6. Learning log
        await self.learning.log_interaction(user_id, message, intent, result)

        result["intent"] = intent
        result["confidence"] = intent_result.get("confidence", 0)
        return result

    async def _execute_tools(self, intent: str, message: str, tools: list,
                             comparison: Optional[Dict] = None,
                             svg_request: bool = False) -> Dict[str, Any]:
        if intent == "image_generation":
            return await self.image.generate(message)
        if intent == "coding":
            return await self.code.handle(message)
        if intent == "networking":
            return await self.network.analyze(message)
        if intent in ("research", "weather", "crypto", "exchange", "country",
                      "dictionary", "joke", "hackernews", "arxiv", "books",
                      "github", "stackoverflow", "nasa", "ip_lookup",
                      "education", "sports", "movie", "video"):
            return await self.research.perform(message, comparison=comparison, svg_request=svg_request)
        if intent == "file_analysis":
            return await self.file.analyze(message)
        # General / chat fallback
        knowledge = await self.knowledge.search(message)
        if knowledge:
            return {
                "success": True,
                "type": "chat",
                "response": knowledge + "\n\n*(From internal knowledge base)*",
                "sources": [],
            }
        # Fallback to research for anything else
        return await self.research.perform(message, comparison=comparison, svg_request=svg_request)


# Singleton
_ai_engine = AIEngine()


async def process_message(message: str, session_id: str, user_id: Optional[int] = None,
                          context: Optional[Dict] = None, **kwargs) -> Dict[str, Any]:
    return await _ai_engine.process(message, session_id, user_id, context, **kwargs)
