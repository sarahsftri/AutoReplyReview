
# Guest Feedback Intelligence + Auto-Reply Studio (Ops v4)
- Streamlit app with enhanced dashboard (date range, filters, risk leaderboard, heatmap, emerging topics, critical incidents)
- Works offline in **dry-run**; switch to your LiteLLM endpoint for real model calls.

## Run (demo, no API key)
```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
echo LLM_DRY_RUN=true > .env   # Windows PowerShell: 'LLM_DRY_RUN=true' | Out-File -Encoding utf8 .env
streamlit run app.py
```

## Real endpoint
Set in `.env`:
```
LLM_BASE_URL=https://litellm.bangka/v1
LLM_MODEL=Qwen3-4B-Instruct-2507
LLM_API_KEY=<your_key>
LLM_DRY_RUN=false
LLM_JSON_MODE=true
```

CSV schema: `timestamp,outlet,brand,platform,rating,text,language,username,order_type`
