"""
Collector pipeline — Week 1 core.
Runs every 10 minutes via scheduler or Railway cron.
"""
from datetime import datetime, timezone
from loguru import logger
from collector.reddit import RedditCollector
from collector.storage import PostStorage
from collector.metrics import MetricsCalculator
from utils.db import get_db


def run_collection():
    """Full collection run: fetch → filter → save → snapshot."""
    start = datetime.now(timezone.utc)
    logger.info(f"=== Collection run started at {start.strftime('%H:%M:%S')} ===")

    collector = RedditCollector()
    storage = PostStorage()
    metrics = MetricsCalculator()

    try:
        # 1. Fetch all posts
        posts = collector.collect_all()
        if not posts:
            logger.warning("No posts collected — check network or Reddit availability")
            return

        # 2. Save new posts to Supabase
        saved, skipped = storage.save_batch(posts)

        # 3. Snapshot engagement for velocity tracking
        # Get existing posts that match collected IDs
        existing_ids = {p["id"] for p in posts}
        db = get_db()
        existing = db.table("raw_posts") \
            .select("reddit_id, engagement, score, num_comments") \
            .in_("reddit_id", list(existing_ids)) \
            .execute()

        if existing.data:
            metrics.snapshot_engagement(existing.data)

        # 4. Update engagement on posts we've seen before
        updated = 0
        for post in posts:
            # Only update if we skipped it (meaning it already existed)
            if not storage.post_exists(post["id"]):
                continue
            storage.update_engagement(post["id"], post["score"], post["num_comments"])
            updated += 1

        # 5. Log run summary
        duration = (datetime.now(timezone.utc) - start).total_seconds()
        logger.info(
            f"=== Run complete in {duration:.1f}s | "
            f"Fetched: {len(posts)} | "
            f"Saved: {saved} | "
            f"Skipped: {skipped} | "
            f"Updated: {updated} ==="
        )

        # 6. Log to Supabase scraper_log
        try:
            db.table("scraper_log").insert({
                "source": "reddit",
                "stories_found": len(posts),
                "stories_saved": saved,
                "error": None,
                "ran_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception as e:
            logger.warning(f"Failed to write scraper log: {e}")

    except Exception as e:
        logger.error(f"Collection run failed: {e}")
        try:
            get_db().table("scraper_log").insert({
                "source": "reddit",
                "stories_found": 0,
                "stories_saved": 0,
                "error": str(e)[:500],
                "ran_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except:
            pass
    finally:
        collector.close()
        # Clean old engagement snapshots
        metrics.cleanup_old_snapshots(keep_hours=24)
