"""
Prediction utilities for ML models.
"""
import pickle
from pathlib import Path
from typing import List, Dict, Any

from utils.logger import get_logger

logger = get_logger("ml.prediction")


class Predictor:
    def __init__(self):
        self.intent_model = None
        self._load_models()

    def _load_models(self):
        intent_path = Path("ml/models/intent_classifier.pkl")
        if intent_path.exists():
            try:
                with open(intent_path, "rb") as f:
                    self.intent_model = pickle.load(f)
                logger.info("Predictor loaded intent model.")
            except Exception as e:
                logger.warning(f"Could not load intent model: {e}")

    def predict_intent(self, text: str) -> Dict[str, Any]:
        if not self.intent_model:
            return {"intent": "general", "confidence": 0.0}
        intent = self.intent_model.predict([text])[0]
        decision = self.intent_model.decision_function([text])[0]
        max_idx = abs(decision).argmax()
        confidence = min(abs(decision[max_idx]) / 2.0, 1.0)
        return {"intent": intent, "confidence": float(confidence)}

    def predict_relevance(self, query: str, documents: List[str]) -> List[float]:
        """Simple TF-IDF cosine similarity for document ranking."""
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        if not documents:
            return []
        vectorizer = TfidfVectorizer(stop_words="english")
        tfidf = vectorizer.fit_transform(documents + [query])
        query_vec = tfidf[-1]
        doc_vecs = tfidf[:-1]
        scores = cosine_similarity(query_vec, doc_vecs).flatten()
        return scores.tolist()
