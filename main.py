"""
Spilled Narrative Intelligence Engine
Full pipeline: collect → cluster (Groq) → generate content (Gemini) → cleanup
"""
import os
import time
import schedule
from loguru import logger
from utils.config import config

os.makedirs("logs", exist_ok=True)


def run_pipeline():
    from datetime import datetime, timezone
    start = datetime.now(timezone.utc)
    logger.info("=" * 50)
    logger.info(f"Pipeline started: {start.strftime('%H:%M:%S')}")

    # ── STEP 1: COLLECT ───────────────────────────────────
    logger.info("Step 1: Collecting posts...")
    try:
        from collector.run import run_collection
        run_collection()
    except Exception as e:
        logger.error(f"Collection failed: {e}")

    # ── STEP 2: CLUSTER + GENERATE ────────────────────────
    logger.info("Step 2: Clustering with Groq + generating with Gemini...")
    try:
        from collector.storage import PostStorage
        from clustering_llm import run_clustering_pipeline

        storage = PostStorage()
        posts = storage.get_recent_posts(hours=6, limit=300)

        if posts:
            logger.info(f"Processing {len(posts)} posts...")
            created, updated = run_clustering_pipeline(posts)
            logger.info(f"Done: {created} narratives created, {updated} updated")
        else:
            logger.info("No new posts to cluster")

    except Exception as e:
        logger.error(f"Clustering failed: {e}")

    # ── STEP 3: LIFECYCLE CLEANUP ─────────────────────────
    logger.info("Step 3: Lifecycle cleanup...")
    try:
        from scoring.lifecycle import LifecycleManager
        LifecycleManager().run_all()
    except Exception as e:
        logger.error(f"Lifecycle failed: {e}")

    # ── DONE ──────────────────────────────────────────────
    duration = (datetime.now(timezone.utc) - start).total_seconds()
    logger.info(f"Pipeline complete in {duration:.1f}s")
    logger.info("=" * 50)


def main():
    logger.info("🫖 Spilled Engine starting up...")
    logger.info(f"Poll interval: every {config.POLL_INTERVAL_MINUTES} minutes")
    logger.info(f"Groq clustering: {'enabled' if config.GROQ_API_KEY else 'MISSING KEY'}")
    logger.info(f"Gemini generation: {'enabled' if config.GEMINI_API_KEY else 'MISSING KEY'}")

    # Run immediately on startup
    run_pipeline()

    # Schedule recurring runs
    schedule.every(config.POLL_INTERVAL_MINUTES).minutes.do(run_pipeline)
    logger.info(f"Scheduler active — every {config.POLL_INTERVAL_MINUTES} minutes")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
    
