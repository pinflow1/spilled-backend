"""
LLM content generator.
Primary: Groq (Llama 3 70B) — fast, generous free tier
Fallback: Gemini 1.5 Flash — when Groq hits rate limit
Last resort: Local NLP extraction

Only called when narrative reaches emerging status (score > 68).
Results cached 24h in Supabase to minimize API calls.
Max 12 LLM calls per day enforced.
"""
import json
import re
from datetime import datetime, timezone, timedelta
from loguru import logger
from utils.config import config
from utils.db import get_db

# Daily call counter — resets at midnight
_daily_calls = {"count": 0, "date": None}
MAX_DAILY_CALLS = 12


def _check_daily_limit() -> bool:
    """Returns True if we can make an LLM call."""
    today = datetime.now(timezone.utc).date().isoformat()
    if _daily_calls["date"] != today:
        _daily_calls["count"] = 0
        _daily_calls["date"] = today
    return _daily_calls["count"] < MAX_DAILY_CALLS


def _increment_daily_calls():
    _daily_calls["count"] += 1


def _build_prompt(narrative: dict, posts: list[dict]) -> str:
    """Build the LLM prompt for a narrative."""
    top_titles = "\n".join(
        f"- {p['title']}" for p in posts[:5]
    )
    subreddits = ", ".join(narrative.get("participating_subs", [])[:6])
    score = narrative.get("narrative_score", 0)
    engagement = narrative.get("total_engagement", 0)

    return f"""You are the intelligence engine for Spilled, a narrative discovery platform for content creators.

Analyze this emerging internet narrative and generate creator-ready intelligence.

NARRATIVE DATA:
Score: {score}/100
Total engagement: {engagement}
Communities: {subreddits}
Post count: {narrative.get('post_count', 0)}

TOP POSTS:
{top_titles}

Generate a JSON response with EXACTLY this structure (no markdown, no backticks, raw JSON only):
{{
  "headline": "One punchy sentence capturing the core story. No clickbait. Max 120 chars.",
  "summary": "2-3 sentences explaining what's happening, why it matters, and why it's spreading.",
  "status_label": "One of: EARLY SIGNAL, SPICY, BOILING",
  "why_spreading": [
    "Reason 1 — specific and insight-driven",
    "Reason 2",
    "Reason 3"
  ],
  "creator_angles": {{
    "youtube": "Specific video angle for YouTube. What's the hook, what's the story arc.",
    "tiktok": "Short-form angle. What's the 30-second version of this story.",
    "threads": "Conversational take. What question does this raise for your audience.",
    "newsletter": "Deep-dive angle. What context or analysis can you add.",
    "podcast": "Discussion angle. What debate or conversation does this start."
  }},
  "hooks": {{
    "curiosity": "Hook that makes people need to know more.",
    "controversy": "Hook that highlights the tension or disagreement.",
    "explainer": "Hook that positions you as the one explaining it.",
    "creator": "Hook specifically for other creators covering this."
  }},
  "opportunity_window": "open|closing|late",
  "best_format": "youtube|tiktok|threads|newsletter|podcast"
}}"""


async def _call_groq(prompt: str) -> dict | None:
    """Call Groq API synchronously."""
    try:
        import httpx
        resp = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {config.GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama3-70b-8192",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1000,
                "temperature": 0.7,
            },
            timeout=20.0,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]
        clean = text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean)
    except Exception as e:
        logger.warning(f"Groq failed: {e}")
        return None


def _call_gemini(prompt: str) -> dict | None:
    """Call Gemini API."""
    try:
        import httpx
        resp = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={config.GEMINI_API_KEY}",
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": 1000, "temperature": 0.7},
            },
            timeout=25.0,
        )
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        clean = text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean)
    except Exception as e:
        logger.warning(f"Gemini failed: {e}")
        return None


def _local_fallback(narrative: dict, posts: list[dict]) -> dict:
    """
    Local NLP fallback when both APIs fail.
    Uses keyword extraction and simple heuristics.
    """
    from collections import Counter
    import re

    all_text = " ".join(p.get("title", "") for p in posts[:10])
    words = re.findall(r'\b[A-Za-z]{4,}\b', all_text)
    stop = {"that","this","with","from","have","they","will","been","were","said","about","their"}
    keywords = [w.lower() for w in words if w.lower() not in stop]
    top_kw = [w for w, _ in Counter(keywords).most_common(5)]

    headline = posts[0]["title"] if posts else narrative.get("headline", "Emerging story")
    score = narrative.get("narrative_score", 0)
    status = "BOILING" if score >= 82 else "SPICY" if score >= 68 else "EARLY SIGNAL"

    return {
        "headline": headline[:120],
        "summary": f"A story about {', '.join(top_kw[:3])} is gaining traction across {narrative.get('subreddit_spread', 1)} communities.",
        "status_label": status,
        "why_spreading": [
            "High engagement across multiple communities",
            "Rapid growth in recent hours",
            "Cross-community discussion forming",
        ],
        "creator_angles": {
            "youtube": f"Deep dive into the {top_kw[0] if top_kw else 'story'} controversy",
            "tiktok": "Quick breakdown of what's happening right now",
            "threads": "What do you think about this?",
            "newsletter": "Analysis and context behind the story",
            "podcast": "Debate: is this as big as it seems?",
        },
        "hooks": {
            "curiosity": f"Why is everyone talking about {top_kw[0] if top_kw else 'this'}?",
            "controversy": "Not everyone agrees on this one",
            "explainer": "Here's what you need to know",
            "creator": "Cover this before it peaks",
        },
        "opportunity_window": "open",
        "best_format": "tiktok",
        "_provider": "local_fallback",
    }


def generate_narrative_content(narrative: dict, posts: list[dict]) -> dict | None:
    """
    Main entry point. Tries Groq → Gemini → local fallback.
    Caches result in Supabase for 24h.
    """
    narrative_id = narrative["id"]

    # Check if already cached and fresh
    try:
        cached_at = narrative.get("ai_generated_at")
        if cached_at:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(cached_at)).total_seconds()
            if age < 86400:  # 24h cache
                logger.debug(f"Using cached AI content for {narrative_id[:8]}")
                return {
                    "headline":       narrative.get("headline"),
                    "summary":        narrative.get("summary"),
                    "creator_angles": narrative.get("creator_angles"),
                    "hooks":          narrative.get("hooks"),
                    "viral_explanation": narrative.get("viral_explanation"),
                }
    except Exception:
        pass

    # Check daily limit
    if not _check_daily_limit():
        logger.warning("Daily LLM limit reached — using local fallback")
        return _local_fallback(narrative, posts)

    prompt = _build_prompt(narrative, posts)
    result = None
    provider = None

    # Try Groq first
    if config.GROQ_API_KEY:
        result = _call_groq(prompt)
        if result:
            provider = "groq"
            _increment_daily_calls()

    # Groq failed — try Gemini
    if not result and config.GEMINI_API_KEY:
        # Only use Gemini for high-potential stories
        if narrative.get("narrative_score", 0) >= 78:
            result = _call_gemini(prompt)
            if result:
                provider = "gemini"
                _increment_daily_calls()

    # Both failed — use local
    if not result:
        result = _local_fallback(narrative, posts)
        provider = "local_fallback"

    if not result:
        return None

    # Save to Supabase
    try:
        db = get_db()
        now = datetime.now(timezone.utc).isoformat()

        # Map status label to our status system
        status_map = {
            "BOILING": "active",
            "SPICY": "emerging",
            "EARLY SIGNAL": "emerging",
        }
        status_label = result.get("status_label", "EARLY SIGNAL")
        db_status = status_map.get(status_label, "emerging")

        db.table("narratives").update({
            "headline":          result.get("headline", narrative.get("headline")),
            "summary":           result.get("summary"),
            "status":            db_status,
            "creator_angles":    result.get("creator_angles"),
            "hooks":             result.get("hooks"),
            "viral_explanation": result.get("why_spreading"),
            "ai_generated_at":   now,
            "ai_provider":       provider,
            "last_updated":      now,
        }).eq("id", narrative_id).execute()

        logger.info(f"Generated content via {provider} for narrative {narrative_id[:8]}...")

    except Exception as e:
        logger.error(f"Error saving AI content: {e}")

    return result
