
from typing import List

def violates_banned(text: str, banned: List[str]) -> List[str]:
    low = text.lower()
    hits = []
    for b in banned:
        if b.lower() in low:
            hits.append(b)
    return hits

def enforce_reply_limits(reply: str, max_len: int = 220) -> str:
    return reply.strip()[:max_len]
