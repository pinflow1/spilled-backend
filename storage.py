from datetime import datetime, timezone
from typing import Optional
from loguru import logger
from utils.db import get_db


class PostStorage:
    def __init__(self):
        self.db = get_db()

    def post_exists(self, reddit_id: str) -> bool:
        """Check if a post already exists by Reddit ID."""
        try:
            result = self.db.table("raw_posts") \
                .select("id") \
                .eq("reddit_id", reddit_id) \
                .limit(1) \
                .execute()
            return len(result.data) > 0
        except Exception as e:
            logger.error(f"Error checking post existence: {e}")
            return False

    def hash_exists(self, content_hash: str) -> bool:
        """Check if a near-duplicate exists by title hash."""
        try:
            result = self.db.table("raw_posts") \
                .select("id") \
                .eq("content_hash", content_hash) \
                .limit(1) \
                .execute()
            return len(result.data) > 0
        except Exception as e:
            logger.error(f"Error checking hash: {e}")
            return False

    def save_post(self, post: dict) -> Optional[str]:
        """Save a single post. Returns saved ID or None if skipped."""
        try:
            # Skip if already exists
            if self.post_exists(post["id"]):
                return None

            # Skip near-duplicates by title hash
            if self.hash_exists(post["content_hash"]):
                logger.debug(f"Near-duplicate skipped: {post['title'][:60]}")
                return None

            row = {
                "reddit_id":    post["id"],
                "title":        post["title"],
                "selftext":     post["selftext"],
                "author":       post["author"],
                "subreddit":    post["subreddit"],
                "score":        post["score"],
                "num_comments": post["num_comments"],
                "upvote_ratio": post["upvote_ratio"],
                "created_utc":  post["created_utc"],
                "permalink":    post["permalink"],
                "url":          post["url"],
                "engagement":   post["engagement"],
                "content_hash": post["content_hash"],
                "flair":        post.get("flair", ""),
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "story_id":     None,  # assigned during clustering
            }

            result = self.db.table("raw_posts").insert(row).execute()
            return result.data[0]["id"] if result.data else None

        except Exception as e:
            logger.error(f"Error saving post '{post.get('title', '')[:50]}': {e}")
            return None

    def update_engagement(self, reddit_id: str, score: int, num_comments: int):
        """Update engagement metrics for an existing post."""
        try:
            engagement = score + (num_comments * 2)
            self.db.table("raw_posts") \
                .update({
                    "score": score,
                    "num_comments": num_comments,
                    "engagement": engagement,
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                }) \
                .eq("reddit_id", reddit_id) \
                .execute()
        except Exception as e:
            logger.error(f"Error updating engagement for {reddit_id}: {e}")

    def save_batch(self, posts: list[dict]) -> tuple[int, int]:
        """
        Save a batch of posts.
        Returns (saved_count, skipped_count).
        """
        saved = 0
        skipped = 0

        for post in posts:
            result = self.save_post(post)
            if result:
                saved += 1
            else:
                skipped += 1

        logger.info(f"Batch saved: {saved} new, {skipped} skipped")
        return saved, skipped

    def get_recent_posts(self, hours: int = 6, limit: int = 500) -> list[dict]:
        """Get recent unclustered posts for the clustering pipeline."""
        try:
            cutoff = datetime.now(timezone.utc).timestamp() - (hours * 3600)
            cutoff_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat()

            result = self.db.table("raw_posts") \
                .select("*") \
                .gte("created_utc", cutoff_iso) \
                .is_("story_id", "null") \
                .order("engagement", desc=True) \
                .limit(limit) \
                .execute()

            return result.data or []
        except Exception as e:
            logger.error(f"Error fetching recent posts: {e}")
            return []

    def get_posts_for_story(self, story_id: str) -> list[dict]:
        """Get all posts belonging to a story."""
        try:
            result = self.db.table("raw_posts") \
                .select("*") \
                .eq("story_id", story_id) \
                .order("engagement", desc=True) \
                .execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error fetching posts for story {story_id}: {e}")
            return []
