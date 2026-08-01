from typing import List, Dict


class ReasoningEngine:
    """
    Simple reasoning layer that maps intents to required tool capabilities.
    In a full AGI system, this would use a planner/graph solver.
    """

    TOOL_MAP = {
        "image_generation": ["image_engine"],
        "coding": ["code_engine"],
        "networking": ["network_engine"],
        "file_analysis": ["file_engine"],
        "research": ["research_engine"],
        "weather": ["research_engine"],
        "crypto": ["research_engine"],
        "exchange": ["research_engine"],
        "country": ["research_engine"],
        "dictionary": ["research_engine"],
        "joke": ["research_engine"],
        "hackernews": ["research_engine"],
        "arxiv": ["research_engine"],
        "books": ["research_engine"],
        "github": ["research_engine"],
        "stackoverflow": ["research_engine"],
        "nasa": ["research_engine"],
        "ip_lookup": ["research_engine"],
        "education": ["research_engine"],
        "sports": ["research_engine"],
        "movie": ["research_engine"],
        "video": ["research_engine"],
        "general": ["knowledge_engine", "research_engine"],
        "writing": ["knowledge_engine", "research_engine"],
        "translation": ["knowledge_engine"],
        "mathematics": ["knowledge_engine"],
        "data_analysis": ["file_engine", "research_engine"],
    }

    def select_tools(self, intent: str, message: str) -> List[str]:
        return self.TOOL_MAP.get(intent, ["research_engine"])

    def plan_steps(self, intent: str, message: str) -> List[Dict]:
        tools = self.select_tools(intent, message)
        return [{"step": i + 1, "tool": t, "status": "pending"} for i, t in enumerate(tools)]
