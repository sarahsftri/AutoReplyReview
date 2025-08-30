
from dotenv import load_dotenv
load_dotenv(override=True) 

import os
import streamlit as st
import pandas as pd
from pathlib import Path
from sqlalchemy import select
from src.db import init_db, get_session, Review, Analysis
from src.models import ReviewInput, BrandVoice
from src.constants import TOPIC_TAXONOMY
from src.agent import run_analysis
from src.guardrails import violates_banned, enforce_reply_limits

st.set_page_config(page_title="Guest Feedback Studio (Ops v4)", page_icon="📝", layout="wide")
st.title("📝 Guest Feedback Intelligence + Auto-Reply Studio (Ops v4)")
st.caption("Analyze reviews, draft bilingual replies, and view ops-ready insights.")

init_db()
session = get_session()

if "api_calls" not in st.session_state:
    st.session_state.api_calls = 0

with st.sidebar:
    st.header("Brand Settings")
    tone = st.text_input("Tone", value="warm, professional, concise")
    banned = st.text_input("Banned terms (comma-separated)", value="guarantee, free forever, 100%")
    voice = BrandVoice(tone=tone, banned=[b.strip() for b in banned.split(",") if b.strip()])

    st.divider()
    st.header("Data")
    uploaded = st.file_uploader("Upload reviews CSV", type=["csv"])
    if st.button("Load Sample Data"):
        p = Path("sample_data/reviews.csv")
        uploaded = p.open("rb")

    st.divider()
    st.header("About")
    st.write(f"**Model:** {os.getenv('LLM_MODEL', 'Qwen3-4B-Instruct-2507')}")
    base_url = os.getenv('LLM_BASE_URL', '(not set)')
    st.write(f"**Endpoint:** {base_url}")
    st.write(f"**Dry-run:** {os.getenv('LLM_DRY_RUN','true')}")
    st.write(f"**JSON mode:** {os.getenv('LLM_JSON_MODE','true')}")
    st.write(f"**API calls this session:** {st.session_state.api_calls}")

# Ingest
if uploaded:
    df = pd.read_csv(uploaded)
    needed = ["timestamp","outlet","brand","platform","rating","text","language","username","order_type"]
    for col in needed:
        if col not in df.columns:
            st.error(f"Missing column: {col}")
            st.stop()
    df["id"] = df.index.map(lambda i: f"rvw_{i+1:04d}")
    inserted = 0
    for _, row in df.iterrows():
        if not session.get(Review, row["id"]):
            session.add(Review(
                id=row["id"], outlet=row["outlet"], brand=row["brand"], platform=row["platform"],
                rating=int(row["rating"]) if pd.notna(row["rating"]) else None,
                language=str(row["language"]) if pd.notna(row["language"]) else None,
                text=str(row["text"]), timestamp=str(row["timestamp"]),
                username=str(row["username"]) if pd.notna(row["username"]) else None,
                order_type=str(row["order_type"]) if pd.notna(row["order_type"]) else None
            ))
            inserted += 1
    session.commit()
    st.success(f"Ingested {inserted} new reviews.")

# Inbox
st.subheader("Inbox")
reviews = session.execute(select(Review)).scalars().all()
analyses = {a.id: a for a in session.execute(select(Analysis)).scalars().all()}
if not reviews:
    st.info("Upload a CSV to get started (see sample in left panel).")
else:
    data = [{
        "id": r.id, "outlet": r.outlet, "brand": r.brand, "platform": r.platform,
        "rating": r.rating, "text": r.text[:80] + ("..." if len(r.text)>80 else ""),
        "has_analysis": "✅" if r.id in analyses else ""
    } for r in reviews]
    st.dataframe(pd.DataFrame(data), use_container_width=True)

    st.divider()
    st.subheader("Analyze & Draft Replies")
    to_analyze_ids = [r.id for r in reviews if r.id not in analyses]
    st.write(f"Pending reviews: **{len(to_analyze_ids)}**")
    if st.button("Run LLM on pending reviews"):
        pending = []
        for r in reviews:
            if r.id in analyses:
                continue
            pending.append(ReviewInput(
                id=r.id, outlet=r.outlet, brand=r.brand, platform=r.platform,
                rating=r.rating, text=r.text, language=r.language
            ))
        if not pending:
            st.info("Nothing to analyze.")
        else:
            outputs = run_analysis(voice, pending)
            st.session_state.api_calls += 1
            saved = 0
            for res in outputs:
                hits_en = violates_banned(res["reply_en"], voice.banned)
                hits_id = violates_banned(res["reply_id"], voice.banned)
                reply_en = enforce_reply_limits(res["reply_en"])
                reply_id = enforce_reply_limits(res["reply_id"])
                session.add(Analysis(
                    id=res["id"],
                    sentiment=res["sentiment"],
                    topics=",".join([t for t in res["topics"] if t in TOPIC_TAXONOMY]),
                    severity=int(res["severity"]),
                    reply_en=reply_en,
                    reply_id=reply_id,
                    status="draft" if (hits_en or hits_id) else "approved"
                ))
                saved += 1
            session.commit()
            st.success(f"Saved {saved} analyses.")

    st.divider()
    st.subheader("Reply Queue")
    analyses = {a.id: a for a in session.execute(select(Analysis)).scalars().all()}
    if not analyses:
        st.info("No analyses yet. Run the LLM first.")
    else:
        rows = []
        for r in reviews:
            a = analyses.get(r.id)
            if not a: continue
            rows.append({
                "id": r.id, "outlet": r.outlet, "brand": r.brand, "platform": r.platform,
                "rating": r.rating, "sentiment": a.sentiment, "severity": a.severity,
                "topics": a.topics, "reply_en": a.reply_en, "reply_id": a.reply_id, "status": a.status
            })
        queue_df = pd.DataFrame(rows)
        st.dataframe(queue_df, use_container_width=True)

        export_sel = st.multiselect("Select rows to export (by id)", queue_df["id"].tolist())
        if st.button("Mark selected as approved"):
            for rid in export_sel:
                a = analyses.get(rid)
                if a: a.status = "approved"
            session.commit()
            st.success("Marked as approved.")

        if st.button("Export approved to CSV"):
            approved = [a for a in analyses.values() if a.status == "approved"]
            if not approved:
                st.info("No approved replies to export.")
            else:
                out = []
                for a in approved:
                    r = session.get(Review, a.id)
                    out.append({
                        "id": a.id, "timestamp": r.timestamp, "outlet": r.outlet, "brand": r.brand,
                        "platform": r.platform, "rating": r.rating, "text": r.text,
                        "sentiment": a.sentiment, "topics": a.topics, "severity": a.severity,
                        "reply_en": a.reply_en, "reply_id": a.reply_id
                    })
                out_df = pd.DataFrame(out)
                st.download_button("Download CSV", out_df.to_csv(index=False).encode("utf-8"), "approved_replies.csv", "text/csv")

    # ===================== Enhanced Dashboard =====================
    st.divider()
    st.subheader("Dashboard & Insights ⭐ (Ops-enhanced)")

    analyses = {a.id: a for a in session.execute(select(Analysis)).scalars().all()}
    if not analyses:
        st.info("Run analyses to see insights.")
    else:
        rows = []
        for r in reviews:
            a = analyses.get(r.id)
            if not a: continue
            rows.append({
                "id": r.id, "timestamp": r.timestamp, "outlet": r.outlet, "brand": r.brand,
                "platform": r.platform, "order_type": r.order_type, "language": r.language,
                "rating": r.rating, "sentiment": a.sentiment, "severity": a.severity, "topics": a.topics, "status": a.status, "text": r.text
            })
        dash = pd.DataFrame(rows)
        if dash.empty:
            st.info("No analyzed rows yet.")
        else:
            # Filters
            dash["ts"] = pd.to_datetime(dash["timestamp"], errors="coerce")
            min_date = dash["ts"].min()
            max_date = dash["ts"].max()
            default_start = (max_date - pd.Timedelta(days=7)) if pd.notna(max_date) else None
            colf1, colf2, colf3 = st.columns([1.2,1,1])
            with colf1:
                st.write("**Date range**")
                date_range = st.date_input(
                    "Select range",
                    value=(default_start.date() if default_start is not None else None,
                           max_date.date() if pd.notna(max_date) else None),
                    key="date_range",
                )
            with colf2:
                brand_sel = st.multiselect("Brand", sorted(dash["brand"].dropna().unique().tolist()))
                outlet_sel = st.multiselect("Outlet", sorted(dash["outlet"].dropna().unique().tolist()))
            with colf3:
                plat_sel = st.multiselect("Platform", sorted(dash["platform"].dropna().unique().tolist()))
                order_sel = st.multiselect("Order type", sorted(dash["order_type"].dropna().unique().tolist()))

            df = dash.copy()
            if isinstance(date_range, (list, tuple)) and len(date_range) == 2 and all(date_range):
                start = pd.to_datetime(str(date_range[0]))
                end = pd.to_datetime(str(date_range[1])) + pd.Timedelta(days=1)
                df = df[(df["ts"] >= start) & (df["ts"] < end)]
            else:
                start = df["ts"].min()
                end = df["ts"].max() + pd.Timedelta(days=1)

            if brand_sel: df = df[df["brand"].isin(brand_sel)]
            if outlet_sel: df = df[df["outlet"].isin(outlet_sel)]
            if plat_sel: df = df[df["platform"].isin(plat_sel)]
            if order_sel: df = df[df["order_type"].isin(order_sel)]

            if df.empty:
                st.info("No rows after filters. Try widening your date range or clearing filters.")
            else:
                def frac(cond_series):
                    total = len(df)
                    return float(cond_series.sum())/total if total else 0.0

                neg_share = frac(df["sentiment"].eq("negative"))
                avg_sev = float(df["severity"].mean()) if len(df) else 0.0
                prev_start = start - pd.Timedelta(days=7)
                prev_end = start
                prev = dash[(dash["ts"] >= prev_start) & (dash["ts"] < prev_end)]
                vol_delta = (len(df) - len(prev)) / (len(prev) if len(prev) else 1)
                pn = df[df["sentiment"].isin(["positive","neutral"])]
                aut = pn[pn["status"].eq("approved")]
                auto_cov = len(aut) / (len(pn) if len(pn) else 1)

                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Negative share", f"{neg_share:.0%}", f"Δ {vol_delta*100:+.0f}% vs prev wk volume")
                k2.metric("Avg severity", f"{avg_sev:.2f}")
                k3.metric("Auto-reply coverage", f"{auto_cov:.0%}")
                k4.metric("Reviews (range)", f"{len(df)}")

                st.write("**Sentiment by Brand**")
                st.bar_chart(df.groupby(["brand","sentiment"]).size().unstack(fill_value=0))

                st.write("**Top Topics**")
                topics_rows = []
                for t in df["topics"]:
                    for one in (t.split(",") if isinstance(t, str) else []):
                        one = one.strip()
                        if one: topics_rows.append(one)
                if topics_rows:
                    tops = pd.Series(topics_rows).value_counts().head(12)
                    st.bar_chart(tops)
                else:
                    st.info("No topics yet.")

                st.write("**Severity by Outlet (avg)**")
                sev = df.groupby("outlet")["severity"].mean().sort_values(ascending=False).head(12)
                st.bar_chart(sev)

                st.write("### Outlet Risk Leaderboard")
                g = df.groupby("outlet").agg(
                    avg_sev=("severity","mean"),
                    neg_share=("sentiment", lambda s: (s=="negative").mean() if len(s) else 0.0),
                    volume=("sentiment","size")
                ).reset_index()
                if len(g) >= 1:
                    mean_v = g["volume"].mean() or 0.0
                    std_v = g["volume"].std(ddof=0) or 1.0
                    g["volume_z"] = (g["volume"] - mean_v) / std_v
                    g["volume_z"] = g["volume_z"].clip(lower=0)
                    g["risk"] = 0.5*g["avg_sev"] + 0.4*g["neg_share"] + 0.1*g["volume_z"]
                    g = g.sort_values(["risk","avg_sev","neg_share"], ascending=False)
                    st.dataframe(g[["outlet","avg_sev","neg_share","volume","risk"]].round(3), use_container_width=True)
                else:
                    st.info("Not enough data to compute leaderboard.")

                st.write("### Topics Heatmap (last selection)")
                tt = df.assign(topic=df["topics"].str.split(",")).explode("topic")
                if not tt.empty:
                    tt["topic"] = tt["topic"].fillna("").str.strip()
                    tt = tt[tt["topic"] != ""]
                    heat = tt.pivot_table(index="outlet", columns="topic", values="id", aggfunc="count", fill_value=0)
                    st.dataframe(heat.style.background_gradient(cmap="Greens"), use_container_width=True)
                else:
                    st.info("No topic data for heatmap.")

                st.write("### Emerging Topics (WoW growth)")
                tt_all = dash.assign(ts=pd.to_datetime(dash["timestamp"], errors="coerce"),
                                     topic=dash["topics"].str.split(",")).explode("topic")
                tt_all["topic"] = tt_all["topic"].fillna("").str.strip()
                tt_all = tt_all[tt_all["topic"] != ""]
                this_w = tt_all[(tt_all["ts"] >= start) & (tt_all["ts"] < end)]
                prev_w = tt_all[(tt_all["ts"] >= prev_start) & (tt_all["ts"] < prev_end)]
                w_this = this_w.groupby("topic").size()
                w_prev = prev_w.groupby("topic").size()
                growth = ((w_this - w_prev) / w_prev.replace(0, 1)).sort_values(ascending=False)
                if not growth.empty:
                    growth_df = growth.rename("wow_growth").to_frame()
                    st.dataframe(growth_df.head(10).style.format({"wow_growth": "{:.0%}"}), use_container_width=True)
                else:
                    st.info("Not enough data to compute growth.")

                st.write("### Critical Incidents (latest)")
                crit = df[(df["sentiment"]=="negative") | (df["severity"]>=4)].copy()
                crit = crit.sort_values("ts", ascending=False).head(15)
                if crit.empty:
                    st.info("No critical incidents in the selected range.")
                else:
                    show = crit[["ts","brand","outlet","platform","topics","severity","text"]].copy()
                    show["text"] = show["text"].apply(lambda s: (s[:120]+"…") if isinstance(s,str) and len(s)>120 else s)
                    st.dataframe(show.rename(columns={"ts":"time"}), use_container_width=True)
