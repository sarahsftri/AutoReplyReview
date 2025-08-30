
import os, json, re, time
import requests

BASE_URL = os.getenv('LLM_BASE_URL', 'http://localhost:8000/v1')
MODEL = os.getenv('LLM_MODEL', 'Qwen3-4B-Instruct-2507')
API_KEY = os.getenv('LLM_API_KEY', '')
DRY_RUN = os.getenv('LLM_DRY_RUN', 'true').lower() == 'true'
JSON_MODE = os.getenv('LLM_JSON_MODE', 'true').lower() == 'true'
TIMEOUT = int(os.getenv('LLM_TIMEOUT', '60'))

SYSTEM_PROMPT = (
    "You are a hospitality guest-experience analyst. "
    "Return STRICT JSON (no extra text). For each item, output: "
    "id, language, sentiment (positive|neutral|negative), topics (from: taste,service,wait_time,cleanliness,value,staff,delivery,packaging,ambience,noise,portion,payment), "
    "severity (1-5), reply_en (<=220 chars), reply_id (<=220 chars). "
    "Decide SENTIMENT primarily from the review TEXT; treat rating as a weak prior. "
    "If text and rating conflict, follow the TEXT. "
    "Always return at least one topic from the taxonomy."
)

def _heuristic_stub(items):
    out = []
    for it in items:
        txt = (it.get("text") or "").lower()
        rating = it.get("rating", 3) or 3
        # Simple text-driven tweak
        neg_kw = ["late","spill","tumpah","dirty","kotor","rude","kasar","refund","cold","uncooked","poison","telat","very late"]
        pos_kw = ["enak","great","love","mantap","lezat","awesome","fast service","puas","worth","terima kasih"]
        score = 0
        if any(k in txt for k in pos_kw): score += 1
        if any(k in txt for k in neg_kw): score -= 1
        if score <= -1: sentiment = "negative"
        elif score >= 1: sentiment = "positive"
        else: sentiment = "positive" if rating >= 4 else "negative" if rating <= 2 else "neutral"

        topics = []
        if any(w in txt for w in ["queue","wait","lama","nunggu","antri","antre"]): topics.append("wait_time")
        if any(w in txt for w in ["tumpah","spill","kemasan","bungkus","bocor","packag"]): topics.append("packaging")
        if any(w in txt for w in ["enak","great","love","mantap","lezat","nice","asin","pahit","asam","gurih","awesome"]): topics.append("taste")
        if any(w in txt for w in ["service","pelayan","pramusaji","ramah","kasir","barista","staff"]): topics.append("service")
        if any(w in txt for w in ["kotor","kebersihan","bersih","clean"]): topics.append("cleanliness")
        if any(w in txt for w in ["portion","porsi","kecil","besar","cukup"]): topics.append("portion")
        if any(w in txt for w in ["ambience","suasana","ramai","noisy","berisik"]): topics.append("ambience")
        if any(w in txt for w in ["delivery","telat","terlambat","late","driver"]): topics.append("delivery")
        if any(w in txt for w in ["mahal","murah","value","worth"]): topics.append("value")
        topics = topics or ["service"]

        severity = 1 if sentiment=="positive" else 5 if sentiment=="negative" else 3
        lang = "id" if re.search(r"[^\x00-\x7F]", it.get("text","")) else "en"
        if sentiment=="negative":
            reply_en = "We’re sorry for the experience. Please DM your order details—we want to make this right."
            reply_id = "Mohon maaf atas pengalaman Anda. Silakan DM detail pesanan—kami akan tindak lanjuti."
        elif sentiment=="positive":
            reply_en = "Thank you for the great review! We’re glad you enjoyed your visit and hope to see you again."
            reply_id = "Terima kasih atas ulasannya! Senang Anda menikmati kunjungannya, sampai jumpa lagi."
        else:
            reply_en = "Thanks for the feedback—we’ll share this with the team and keep improving."
            reply_id = "Terima kasih atas masukannya—kami akan terus perbaiki."

        out.append({
            "id": it["id"], "language": lang, "sentiment": sentiment, "topics": topics,
            "severity": severity, "reply_en": reply_en, "reply_id": reply_id
        })
    return out

def analyze_batch(brand_voice, items, max_retries=2):
    if DRY_RUN:
        return _heuristic_stub(items)

    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL,
        "messages": [
            {"role":"system","content": SYSTEM_PROMPT},
            {"role":"user","content": json.dumps({"brand_voice": brand_voice, "items": items})}
        ],
        "temperature": 0.2
    }
    if JSON_MODE:
        payload["response_format"] = {"type":"json_object"}

    url = f"{BASE_URL}/chat/completions"
    last_err = None
    for attempt in range(max_retries + 1):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
            r.raise_for_status()
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            return json.loads(content)
        except Exception as e:
            last_err = e
            time.sleep(0.8 * (attempt + 1))
    raise RuntimeError(f"LLM call failed after retries: {last_err}")
