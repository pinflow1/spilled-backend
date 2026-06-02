"""
Thread builder — converts narrative posts into
the thread format the React frontend expects.
Saves to thread_posts table in Supabase.
"""
from datetime import datetime, timezone
from loguru import logger
from utils.db import get_db


def _format_time_ago(created_utc: str) -> str:
    """Convert ISO timestamp to human readable."""
    try:
        dt = datetime.fromisoformat(created_utc)
        diff = (datetime.now(timezone.utc) - dt).total_seconds()
        mins = int(diff / 60)
        hours = int(diff / 3600)
        if mins < 60:
            return f"{mins}m ago"
        if hours < 24:
            return f"{hours}h ago"
        return f"{int(hours/24)}d ago"
    except Exception:
        return "recently"


def build_thread(narrative_id: str, posts: list[dict], ai_content: dict = None) -> bool:
    """
    Build thread posts for a narrative and save to Supabase.
    Thread format: each post becomes a thread entry.
    First post = context setter, last = developing marker.
    """
    try:
        db = get_db()

        # Check if thread already exists
        existing = db.table("thread_posts") \
            .select("id") \
            .eq("story_id", narrative_id) \
            .limit(1) \
            .execute()

        if existing.data:
            # Update last post as developing if story is still active
            _update_developing_flag(narrative_id, db)
            return True

        if not posts:
            return False

        # Sort posts by engagement
        sorted_posts = sorted(posts, key=lambda p: p.get("engagement", 0), reverse=True)

        thread_posts = []

        # If we have AI content, use it to enrich the thread
        why_spreading = ai_content.get("why_spreading", []) if ai_content else []

        for i, post in enumerate(sorted_posts[:6]):  # max 6 thread posts
            is_last = i == len(sorted_posts[:6]) - 1

            content = post.get("title", "")

            # Add body if it has meaningful selftext
            selftext = (post.get("selftext") or "").strip()
            if selftext and len(selftext) > 50:
                content += f" — {selftext[:200]}"

            # Enrich with AI insights if available
            if i == 0 and why_spreading:
                content += f" {why_spreading[0]}" if why_spreading else ""

            thread_posts.append({
                "story_id":      narrative_id,
                "content":       content[:500],
                "source":        f"Reddit r/{post.get('subreddit', 'unknown')}",
                "post_time":     _format_time_ago(post.get("created_utc", "")),
                "is_developing": is_last,
                "order_index":   i,
            })

        if thread_posts:
            db.table("thread_posts").insert(thread_posts).execute()
            logger.debug(f"Built {len(thread_posts)} thread posts for {narrative_id[:8]}")
            return True

        return False

    except Exception as e:
        logger.error(f"Error building thread for {narrative_id}: {e}")
        return False


def _update_developing_flag(narrative_id: str, db):
    """Update the last thread post's is_developing flag."""
    try:
        posts = db.table("thread_posts") \
            .select("id") \
            .eq("story_id", narrative_id) \
            .order("order_index", desc=True) \
            .limit(1) \
            .execute()

        if posts.data:
            db.table("thread_posts") \
                .update({"is_developing": True}) \
                .eq("id", posts.data[0]["id"]) \
                .execute()
    except Exception as e:
        logger.warning(f"Could not update developing flag: {e}")
