"""
Machine Learning Training Pipeline.
Retrains intent classifier and other models from accumulated data.
"""
import os
import pickle
from typing import List
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report

from utils.logger import get_logger

logger = get_logger("ml.training")
MODEL_DIR = Path("ml/models")
MODEL_DIR.mkdir(parents=True, exist_ok=True)


class TrainingPipeline:
    def __init__(self):
        self.pipeline: Pipeline | None = None

    def train_intent_classifier(self, texts: List[str], labels: List[str], validate: bool = True):
        """Train or retrain the intent classifier."""
        if len(texts) < 10:
            logger.warning("Not enough training data (minimum 10 samples).")
            return False

        if validate:
            X_train, X_test, y_train, y_test = train_test_split(texts, labels, test_size=0.2, random_state=42)
        else:
            X_train, y_train = texts, labels
            X_test, y_test = None, None

        self.pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), stop_words="english", max_features=5000)),
            ("clf", LinearSVC(C=1.0, max_iter=2000)),
        ])
        self.pipeline.fit(X_train, y_train)

        if validate and X_test:
            preds = self.pipeline.predict(X_test)
            report = classification_report(y_test, preds, output_dict=True)
            logger.info(f"Validation accuracy: {report['accuracy']:.3f}")

        # Save
        model_path = MODEL_DIR / "intent_classifier.pkl"
        with open(model_path, "wb") as f:
            pickle.dump(self.pipeline, f)
        logger.info(f"Intent classifier saved to {model_path}")
        return True

    def train_from_db(self):
        """Load training data from database and retrain."""
        # Placeholder: in production, query LearningLog and Message tables
        logger.info("DB training placeholder — implement data extraction from database.")
        pass


# Convenience
def retrain_intent(texts: List[str], labels: List[str]):
    pipe = TrainingPipeline()
    return pipe.train_intent_classifier(texts, labels)
