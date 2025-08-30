
from typing import List, Dict
from .llm import analyze_batch
from .models import ReviewInput, BrandVoice, ReviewAnalysis
from .constants import TOPIC_TAXONOMY

def run_analysis(voice: BrandVoice, reviews: List[ReviewInput]) -> List[Dict]:
    items = [{
        "id": r.id, "outlet": r.outlet, "brand": r.brand, "platform": r.platform,
        "rating": r.rating, "text": r.text, "language": r.language
    } for r in reviews]
    raw = analyze_batch(voice.model_dump(), items)
    out = []
    for obj in raw:
        try:
            parsed = ReviewAnalysis(**obj)
        except Exception:
            continue
        out.append(parsed.model_dump())
    return out
