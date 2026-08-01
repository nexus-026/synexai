import re
import html
import math
from typing import List, Dict, Any
from collections import Counter


def extract_keywords(text: str, max_kw: int = 8) -> List[str]:
    clean = re.sub(r"[^\w\s]", " ", text.lower())
    words = clean.split()
    stop = {
        "the","a","an","is","are","was","were","be","been","being","have","has","had","do","does","did",
        "will","would","could","should","may","might","must","shall","can","need","to","of","in","for",
        "on","with","at","by","from","as","into","through","during","before","after","above","below",
        "between","under","and","but","or","yet","so","if","because","although","while","where","when",
        "that","which","who","whom","whose","what","this","these","those","i","me","my","we","our","you",
        "your","he","him","his","she","her","it","its","they","them","their","am","how","why","all","any",
        "both","each","few","more","most","other","some","such","no","nor","not","only","own","same","than",
        "too","very","just","now","also","get","like","make","way","know","take","see","come","think","look",
        "want","give","use","find","tell","ask","work","seem","feel","try","leave","call","good","new","first",
        "last","long","great","little","old","right","big","high","different","small","large","next","early",
        "young","important","public","bad","able",
    }
    filtered = [w for w in words if len(w) > 2 and w not in stop]
    freq = Counter(filtered)
    return [w for w, _ in freq.most_common(max_kw)]


def summarize_text(text: str, max_length: int = 800) -> str:
    if not text or len(text) <= max_length:
        return text.strip()
    sentences = re.split(r'(?<=[.!?])\s+', text)
    if len(sentences) <= 2:
        return text[:max_length].strip()
    keywords = extract_keywords(text, 15)
    scored = []
    for i, sent in enumerate(sentences):
        score = sum(sent.lower().count(k) for k in keywords)
        if i == 0:
            score += 3
        if i == len(sentences) - 1:
            score += 2
        scored.append((score, i, sent))
    scored.sort(reverse=True)
    top = sorted(scored[:5], key=lambda x: x[1])
    summary = ""
    for _, _, sent in top:
        if len(summary) + len(sent) > max_length:
            break
        summary += " " + sent
    return summary.strip() or text[:max_length].strip()


def extract_readable_text(html_text: str) -> str:
    if not html_text:
        return ""
    text = re.sub(r'<script\b[^>]*>.*?</script>', ' ', html_text, flags=re.S)
    text = re.sub(r'<style\b[^>]*>.*?</style>', ' ', text, flags=re.S)
    text = re.sub(r'<nav\b[^>]*>.*?</nav>', ' ', text, flags=re.S)
    text = re.sub(r'<footer\b[^>]*>.*?</footer>', ' ', text, flags=re.S)
    text = re.sub(r'<header\b[^>]*>.*?</header>', ' ', text, flags=re.S)
    text = re.sub(r'<aside\b[^>]*>.*?</aside>', ' ', text, flags=re.S)
    text = re.sub(r'</(p|div|h[1-6]|li|tr|blockquote)>', '\n', text, flags=re.I)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    text = re.sub(r'[\t ]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def extract_title(html_text: str) -> str:
    m = re.search(r'<title[^>]*>(.*?)</title>', html_text, re.S | re.I)
    if m:
        return html.unescape(m.group(1)).strip()
    m = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', html_text, re.I)
    if m:
        return html.unescape(m.group(1)).strip()
    m = re.search(r'<h1[^>]*>(.*?)</h1>', html_text, re.S | re.I)
    if m:
        return re.sub(r'<[^>]+>', '', m.group(1)).strip()
    return "Untitled"


def extract_meta_description(html_text: str) -> str:
    m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']', html_text, re.I)
    if m:
        return html.unescape(m.group(1)).strip()
    m = re.search(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']', html_text, re.I)
    if m:
        return html.unescape(m.group(1)).strip()
    return ""


def cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def extract_topic(query: str) -> str:
    lower = query.lower()
    clean = re.sub(r'\b(what|who|where|when|why|how|is|are|was|were|do|does|did|can|could|would|should|will|the|a|an|about|explain|tell|me|describe|compare)\b', ' ', lower)
    clean = re.sub(r'[^\w\s]', ' ', clean)
    words = [w for w in clean.split() if w]
    words.sort(key=len, reverse=True)
    return ' '.join(words[:3])


def detect_follow_up(query: str, last_topic: str) -> bool:
    q = query.lower().strip()
    if len(query) < 25:
        return True
    follow_words = ['it','that','they','them','their','he','she','his','her','this','these','those','the','also','another','more','else','too']
    for w in follow_words:
        if q.startswith(w) or re.search(rf'\b{re.escape(w)}\b', q):
            return True
    if last_topic:
        tw = last_topic.lower().split()
        matches = sum(1 for w in tw if len(w) > 3 and w in q)
        if matches >= 1:
            return True
    return False


def detect_comparison(query: str) -> Dict[str, Any] | None:
    patterns = [
        (r'(.*?)\s+(?:vs|versus)\s+(.+)', 'vs'),
        (r'(?:compare|comparison of|comparing)\s+(.+?)\s+(?:and|with|to)\s+(.+)', 'compare'),
        (r'(?:difference between|differences between)\s+(.+?)\s+(?:and|vs)\s+(.+)', 'diff'),
        (r'(?:should I choose|which is better|which one is better|pros and cons of)\s+(.+?)\s+(?:or|vs|versus)\s+(.+)', 'better'),
    ]
    for pat, typ in patterns:
        m = re.search(pat, query, re.I)
        if m:
            return {"type": typ, "a": m.group(1).strip(' ?'), "b": m.group(2).strip(' ?')}
    return None


def build_comparison_table(info_a: Dict, info_b: Dict, label_a: str, label_b: str) -> str:
    headers = ["Feature", label_a, label_b]
    rows = []
    all_keys = sorted(set(info_a.keys()) | set(info_b.keys()))
    for key in all_keys:
        val_a = info_a.get(key, "—")
        val_b = info_b.get(key, "—")
        rows.append(f"| {key.capitalize()} | {val_a} | {val_b} |")
    table = f"| {' | '.join(headers)} |\n"
    table += f"|{' --- |' * len(headers)}\n"
    table += "\n".join(rows)
    return table


def generate_educational_svg(topic: str, svg_type: str = "diagram") -> str:
    safe = html.escape(topic, quote=True)
    if svg_type == "cycle":
        return f'''<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300" viewBox="0 0 400 300">
  <rect width="400" height="300" fill="#f8fafc" rx="12"/>
  <circle cx="200" cy="150" r="80" fill="none" stroke="#3b82f6" stroke-width="3" stroke-dasharray="10,5"/>
  <text x="200" y="155" text-anchor="middle" font-size="14" fill="#1e293b" font-family="sans-serif">{safe}</text>
  <text x="200" y="30" text-anchor="middle" font-size="16" font-weight="bold" fill="#0f172a">Cycle Diagram</text>
  <path d="M 280 150 L 300 150 L 295 145 M 300 150 L 295 155" stroke="#3b82f6" stroke-width="2" fill="none"/>
</svg>'''
    elif svg_type == "compare":
        return f'''<svg xmlns="http://www.w3.org/2000/svg" width="500" height="200" viewBox="0 0 500 200">
  <rect width="500" height="200" fill="#f8fafc" rx="12"/>
  <rect x="30" y="50" width="200" height="120" fill="#dbeafe" stroke="#3b82f6" stroke-width="2" rx="8"/>
  <rect x="270" y="50" width="200" height="120" fill="#dcfce7" stroke="#22c55e" stroke-width="2" rx="8"/>
  <text x="130" y="110" text-anchor="middle" font-size="14" fill="#1e40af" font-family="sans-serif">A</text>
  <text x="370" y="110" text-anchor="middle" font-size="14" fill="#166534" font-family="sans-serif">B</text>
  <text x="250" y="30" text-anchor="middle" font-size="16" font-weight="bold" fill="#0f172a">{safe}</text>
  <path d="M 235 110 L 265 110 M 255 105 L 265 110 L 255 115" stroke="#64748b" stroke-width="2" fill="none"/>
</svg>'''
    else:
        return f'''<svg xmlns="http://www.w3.org/2000/svg" width="400" height="250" viewBox="0 0 400 250">
  <rect width="400" height="250" fill="#f8fafc" rx="12"/>
  <text x="200" y="30" text-anchor="middle" font-size="16" font-weight="bold" fill="#0f172a">{safe}</text>
  <rect x="50" y="60" width="300" height="40" fill="#e0e7ff" stroke="#6366f1" stroke-width="2" rx="6"/>
  <text x="200" y="85" text-anchor="middle" font-size="13" fill="#312e81">Step 1: Input</text>
  <path d="M 200 100 L 200 120" stroke="#6366f1" stroke-width="2"/>
  <rect x="50" y="125" width="300" height="40" fill="#e0e7ff" stroke="#6366f1" stroke-width="2" rx="6"/>
  <text x="200" y="150" text-anchor="middle" font-size="13" fill="#312e81">Step 2: Process</text>
  <path d="M 200 165 L 200 185" stroke="#6366f1" stroke-width="2"/>
  <rect x="50" y="190" width="300" height="40" fill="#e0e7ff" stroke="#6366f1" stroke-width="2" rx="6"/>
  <text x="200" y="215" text-anchor="middle" font-size="13" fill="#312e81">Step 3: Output</text>
</svg>'''
