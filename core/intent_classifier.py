import os
import re
import pickle
from typing import List, Dict
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
from sklearn.pipeline import Pipeline

from utils.logger import get_logger

logger = get_logger("intent_classifier")

INTENTS = [
    "general", "coding", "research", "image_generation", "file_analysis",
    "education", "mathematics", "networking", "voice", "data_analysis",
    "writing", "translation", "weather", "crypto", "exchange", "country",
    "dictionary", "joke", "hackernews", "arxiv", "books", "github",
    "stackoverflow", "nasa", "ip_lookup", "sports", "movie", "video"
]

MODEL_PATH = Path("ml/models/intent_classifier.pkl")


class IntentClassifier:
    def __init__(self):
        self.pipeline: Pipeline | None = None
        self.rules = self._build_rules()
        self._load_or_init()

    def _build_rules(self) -> List[tuple]:
        return [
            (r'\b(generate|create|make|draw|design|render)\s+(an?\s+)?(image|picture|photo|logo|art|wallpaper|avatar)\b', "image_generation"),
            (r'\b(show\s+me\s+(an?\s+)?(image|picture|photo))\b', "image_generation"),
            (r'\b(write|generate|create|make|build|develop)\s+(a\s+)?(code|script|function|class|program|app|website|page|form|api)\b', "coding"),
            (r'\b(html|css|javascript|js|php|python|sql|c\+\+|c#|java)\s+(code|script|snippet)\b', "coding"),
            (r'\b(debug|fix)\s+(my\s+)?(code|script|bug)\b', "coding"),
            (r'\b(ping|traceroute|trace\s*route|dns|whois|ip\s+address|network|subnet|cidr|port\s+scan|open\s+ports?|ssl\s+cert|geoip|is\s+\w+\s+(up|down|reachable))\b', "networking"),
            (r'\b(weather|temperature|forecast|rain|snow|sunny|cloudy)\s+(?:in|at|for)?\s+([a-z\s]+)', "weather"),
            (r'\b(weather|temperature|forecast)\b', "weather"),
            (r'\b(bitcoin|ethereum|crypto|cryptocurrency|btc|eth|price\s+of)\b', "crypto"),
            (r'\b(exchange\s+rate|convert|usd\s+to|eur\s+to|gbp\s+to|currency)\b', "exchange"),
            (r'\b(country|capital|population|flag|language)\s+(?:of|in)\s+([a-z\s]+)', "country"),
            (r'\b(define|definition|meaning|what\s+does\s+\w+\s+mean)\b', "dictionary"),
            (r'\b(joke|funny|humor|laugh|tell\s+me\s+a\s+joke)\b', "joke"),
            (r'\b(hacker\s+news|hn|tech\s+news|startup\s+news)\b', "hackernews"),
            (r'\b(arxiv|paper|research|scientific\s+paper|academic)\b', "arxiv"),
            (r'\b(book|novel|author|read|literature)\b', "books"),
            (r'\b(github|repository|repo|code\s+on\s+github|open\s+source)\b', "github"),
            (r'\b(stack\s+overflow|stackoverflow|coding\s+question|programming\s+help)\b', "stackoverflow"),
            (r'\b(nasa|space|astronomy|planet|galaxy|apod)\b', "nasa"),
            (r'\b(ip\s+address|my\s+ip|geolocation|where\s+is\s+this\s+ip)\b', "ip_lookup"),
            (r'\b(openalex|academic\s+paper|journal\s+article|scholarly|research\s+paper|citation)\b', "education"),
            (r'\b(crossref|doi|journal|publication|peer\s+review|science\s+paper)\b', "education"),
            (r'\b(team|player|match|league|football|basketball|soccer|sport|sports|nba|nfl|fifa|uefa|score)\b', "sports"),
            (r'\b(movie|film|actor|director|cinema|hollywood|oscar|imdb)\b', "movie"),
            (r'\b(video|youtube|clip|watch)\b', "video"),
            (r'\b(what\s+is|who\s+is|where\s+is|define|explain|compare|latest|news)\b', "research"),
            (r'\?$', "research"),
        ]

    def _load_or_init(self):
        if MODEL_PATH.exists():
            try:
                with open(MODEL_PATH, "rb") as f:
                    self.pipeline = pickle.load(f)
                logger.info("Intent classifier model loaded.")
                return
            except Exception as e:
                logger.warning(f"Failed to load model: {e}")
        self._train_default()

    def _train_default(self):
        # Minimal default training data
        training_data = [
            ("hello how are you", "general"),
            ("what is the weather today", "weather"),
            ("generate an image of a cat", "image_generation"),
            ("write a python function to sort a list", "coding"),
            ("what is machine learning", "research"),
            ("analyze this pdf file", "file_analysis"),
            ("tell me a joke", "joke"),
            ("convert 100 usd to eur", "exchange"),
            ("what is the capital of france", "country"),
            ("define serendipity", "dictionary"),
            ("latest hacker news", "hackernews"),
            ("search for papers on quantum computing", "arxiv"),
            ("find books about python", "books"),
            ("github repos for machine learning", "github"),
            ("stackoverflow question about arrays", "stackoverflow"),
            ("nasa picture of the day", "nasa"),
            ("what is my ip address", "ip_lookup"),
            ("research openalex papers", "education"),
            ("who won the football match", "sports"),
            ("movie info about inception", "movie"),
            ("find youtube videos about cooking", "video"),
            ("ping google.com", "networking"),
            ("write an essay about climate change", "writing"),
            ("translate hello to french", "translation"),
            ("calculate 25 times 4", "mathematics"),
            ("analyze this csv data", "data_analysis"),
            ("read this document for me", "file_analysis"),
        ]
        texts, labels = zip(*training_data)
        self.pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), stop_words="english")),
            ("clf", LinearSVC()),
        ])
        self.pipeline.fit(texts, labels)
        self._save_model()
        logger.info("Intent classifier trained with default data.")

    def _save_model(self):
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(MODEL_PATH, "wb") as f:
            pickle.dump(self.pipeline, f)

    def classify(self, text: str) -> Dict[str, any]:
        text_lower = text.lower()

        # Rule-based first (high precision)
        for pattern, intent in self.rules:
            if re.search(pattern, text_lower, re.I):
                return {"intent": intent, "confidence": 1.0, "method": "rule"}

        # ML fallback
        if self.pipeline:
            intent = self.pipeline.predict([text])[0]
            # Approximate confidence via decision function distance
            decision = self.pipeline.decision_function([text])[0]
            max_idx = abs(decision).argmax()
            confidence = min(abs(decision[max_idx]) / 2.0, 1.0)
            return {"intent": intent, "confidence": float(confidence), "method": "ml"}

        return {"intent": "general", "confidence": 0.0, "method": "fallback"}

    def train(self, texts: List[str], labels: List[str]):
        if self.pipeline is None:
            self._train_default()
        # Partial retraining with new data would require incremental learning;
        # for simplicity, we retrain from accumulated dataset.
        # In production, store dataset in DB and retrain periodically.
        logger.info(f"Retraining intent classifier with {len(texts)} new samples.")
        self.pipeline.fit(texts, labels)
        self._save_model()


# Singleton
_classifier = IntentClassifier()


def classify_intent(text: str) -> Dict[str, any]:
    return _classifier.classify(text)


def train_intent(texts: List[str], labels: List[str]):
    _classifier.train(texts, labels)
