"""
Story lifecycle management.
Handles cooling, archiving, and cleanup of old narratives.
"""
from datetime import datetime, timezone, timedelta
from loguru import logger
from utils.db import get_db
from utils.config import config


class LifecycleManager:
    def __init__(self):
        self.db = get_db()

    def _hours_since(self, iso_timestamp: str) -> float:
        try:
            dt = datetime.fromisoformat(iso_timestamp)
            return (datetime.now(timezone.utc) - dt).total_seconds() / 3600
        except Exception:
            return 999.0

    def move_to_cooling(self) -> int:
        """Move stale narratives to cooling status."""
        try:
            result = self.db.table("narratives") \
                .select("id, narrative_score, last_active, last_updated") \
                .in_("status", ["emerging", "active"]) \
                .execute()

            moved = 0
            for n in (result.data or []):
                hours_inactive = self._hours_since(n["last_active"])
                score = n.get("narrative_score", 0)

                should_cool = (
                    score < config.COOLING_THRESHOLD or
                    hours_inactive > config.COOLING_NO_ACTIVITY_HOURS
                )

                if should_cool:
                    self.db.table("narratives").update({
                        "status": "cooling",
                        "last_updated": datetime.now(timezone.utc).isoformat(),
                    }).eq("id", n["id"]).execute()
                    moved += 1

            if moved:
                logger.info(f"Moved {moved} narratives to cooling")
            return moved

        except Exception as e:
            logger.error(f"Error in move_to_cooling: {e}")
            return 0

    def archive_cooling(self) -> int:
        """Archive narratives that have been cooling too long."""
        try:
            result = self.db.table("narratives") \
                .select("id, last_updated") \
                .eq("status", "cooling") \
                .execute()

            archived = 0
            now = datetime.now(timezone.utc).isoformat()

            for n in (result.data or []):
                hours_cooling = self._hours_since(n["last_updated"])
                if hours_cooling >= config.ARCHIVE_AFTER_COOLING_HOURS:
                    self.db.table("narratives").update({
                        "status": "archived",
                        "archived_at": now,
                        "last_updated": now,
                    }).eq("id", n["id"]).execute()
                    archived += 1

            if archived:
                logger.info(f"Archived {archived} cooling narratives")
            return archived

        except Exception as e:
            logger.error(f"Error in archive_cooling: {e}")
            return 0

    def hard_archive_old(self) -> int:
        """Force archive anything older than 72 hours regardless of status."""
        try:
            cutoff = (
                datetime.now(timezone.utc) - timedelta(hours=config.HARD_ARCHIVE_HOURS)
            ).isoformat()

            result = self.db.table("narratives") \
                .update({
                    "status": "archived",
                    "archived_at": datetime.now(timezone.utc).isoformat(),
                }) \
                .lt("first_seen", cutoff) \
                .not_.eq("status", "archived") \
                .execute()

            count = len(result.data or [])
            if count:
                logger.info(f"Hard archived {count} old narratives")
            return count

        except Exception as e:
            logger.error(f"Error in hard_archive_old: {e}")
            return 0

    def cleanup_old_posts(self) -> int:
        """Delete raw posts older than 72 hours to keep DB lean."""
        try:
            cutoff = (
                datetime.now(timezone.utc) - timedelta(hours=config.HARD_ARCHIVE_HOURS)
            ).isoformat()

            result = self.db.table("raw_posts") \
                .delete() \
                .lt("created_utc", cutoff) \
                .execute()

            count = len(result.data or [])
            if count:
                logger.info(f"Deleted {count} old raw posts")
            return count

        except Exception as e:
            logger.error(f"Error cleaning old posts: {e}")
            return 0

    def run_all(self):
        """Run full lifecycle management cycle."""
        logger.info("Running lifecycle management...")
        cooled   = self.move_to_cooling()
        archived = self.archive_cooling()
        hard     = self.hard_archive_old()
        cleaned  = self.cleanup_old_posts()
        logger.info(
            f"Lifecycle: {cooled} cooled, {archived} archived, "
            f"{hard} force-archived, {cleaned} posts deleted"
        )
