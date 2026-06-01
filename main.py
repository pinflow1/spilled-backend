"""
Spilled Narrative Intelligence Engine
Entry point — runs the collector on a schedule.
"""
import time
import schedule
from loguru import logger
from collector.run import run_collection
from utils.config import config
import os

os.makedirs("logs", exist_ok=True)

def main():
    logger.info("🫖 Spilled Engine starting up...")
    logger.info(f"Poll interval: every {config.POLL_INTERVAL_MINUTES} minutes")
    logger.info(f"Min upvotes: {config.MIN_UPVOTES} | Min comments: {config.MIN_COMMENTS}")
    logger.info(f"Monitoring {len(config.SUBREDDITS)} subreddits + {len(config.GLOBAL_ENDPOINTS)} global feeds")

    # Run once immediately on startup
    logger.info("Running initial collection...")
    run_collection()

    # Schedule recurring runs
    schedule.every(config.POLL_INTERVAL_MINUTES).minutes.do(run_collection)
    logger.info(f"Scheduler active — next run in {config.POLL_INTERVAL_MINUTES} minutes")

    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == "__main__":
    main()
