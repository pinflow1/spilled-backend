from datetime import datetime, timezone
from loguru import logger
from utils.db import get_db


class MetricsCalculator:
    def __init__(self):
        self.db = get_db()

    def calculate_velocity(self, reddit_id: str, current_engagement: int) -> float:
        """
        Calculate engagement velocity (engagements per minute).
        Uses historical snapshots stored in engagement_history.
        """
        try:
            # Get engagement from 30 minutes ago
            result = self.db.table("engagement_history") \
                .select("engagement, recorded_at") \
                .eq("reddit_id", reddit_id) \
                .order("recorded_at", desc=True) \
                .limit(10) \
                .execute()

            if not result.data or len(result.data) < 2:
                return 0.0

            oldest = result.data[-1]
            oldest_engagement = oldest["engagement"]
            oldest_time = datetime.fromisoformat(oldest["recorded_at"])
            now = datetime.now(timezone.utc)

            minutes_elapsed = max((now - oldest_time).total_seconds() / 60, 1)
            velocity = (current_engagement - oldest_engagement) / minutes_elapsed

            return max(velocity, 0.0)

        except Exception as e:
            logger.error(f"Error calculating velocity for {reddit_id}: {e}")
            return 0.0

    def calculate_growth_rate(self, reddit_id: str, current_engagement: int) -> float:
        """
        Growth rate vs 30 minutes ago.
        Returns a multiplier: 1.0 = 100% growth, 0.0 = no growth.
        """
        try:
            thirty_mins_ago = datetime.now(timezone.utc).timestamp() - (30 * 60)
            cutoff = datetime.fromtimestamp(thirty_mins_ago, tz=timezone.utc).isoformat()

            result = self.db.table("engagement_history") \
                .select("engagement") \
                .eq("reddit_id", reddit_id) \
                .lte("recorded_at", cutoff) \
                .order("recorded_at", desc=True) \
                .limit(1) \
                .execute()

            if not result.data:
                return 0.0

            past_engagement = result.data[0]["engagement"]
            growth = (current_engagement - past_engagement) / max(past_engagement, 1)
            return max(growth, 0.0)

        except Exception as e:
            logger.error(f"Error calculating growth rate: {e}")
            return 0.0

    def snapshot_engagement(self, posts: list[dict]):
        """
        Save an engagement snapshot for each post.
        Called after every collection run.
        """
        try:
            now = datetime.now(timezone.utc).isoformat()
            rows = [
                {
                    "reddit_id":   post["reddit_id"],
                    "engagement":  post["engagement"],
                    "score":       post["score"],
                    "num_comments": post["num_comments"],
                    "recorded_at": now,
                }
                for post in posts
            ]
            if rows:
                self.db.table("engagement_history").insert(rows).execute()
                logger.debug(f"Snapshotted {len(rows)} engagement records")
        except Exception as e:
            logger.error(f"Error snapshotting engagement: {e}")

    def cleanup_old_snapshots(self, keep_hours: int = 24):
        """Delete engagement history older than keep_hours."""
        try:
            from datetime import timedelta
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=keep_hours)).isoformat()
            self.db.table("engagement_history") \
                .delete() \
                .lt("recorded_at", cutoff) \
                .execute()
            logger.debug(f"Cleaned engagement history older than {keep_hours}h")
        except Exception as e:
            logger.error(f"Error cleaning snapshots: {e}")
