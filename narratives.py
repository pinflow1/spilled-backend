"""
Converts raw clusters into narrative records in Supabase.
Handles new narrative creation and updating existing ones.
"""
import uuid
from datetime import datetime, timezone
from loguru import logger
from utils.db import get_db


class NarrativeStorage:
    def __init__(self):
        self.db = get_db()

    def _find_existing_narrative(self, cluster: dict) -> dict | None:
        """
        Check if a narrative already exists for this cluster.
        Match by checking if any post in the cluster is already
        assigned to a narrative.
        """
        try:
            reddit_ids = [p["reddit_id"] for p in cluster["posts"] if "reddit_id" in p]
            if not reddit_ids:
                return None

            result = self.db.table("raw_posts") \
                .select("story_id") \
                .in_("reddit_id", reddit_ids) \
                .not_.is_("story_id", "null") \
                .limit(1) \
                .execute()

            if result.data and result.data[0]["story_id"]:
                story_id = result.data[0]["story_id"]
                narrative = self.db.table("narratives") \
                    .select("*") \
                    .eq("id", story_id) \
                    .limit(1) \
                    .execute()
                return narrative.data[0] if narrative.data else None

            return None
        except Exception as e:
            logger.error(f"Error finding existing narrative: {e}")
            return None

    def create_narrative(self, cluster: dict) -> str | None:
        """Create a new narrative from a cluster. Returns narrative ID."""
        try:
            now = datetime.now(timezone.utc).isoformat()
            narrative_id = str(uuid.uuid4())

            row = {
                "id": narrative_id,
                "headline": cluster["representative_title"][:500],
                "status": "emerging",
                "narrative_score": 0.0,
                "opportunity_score": 0.0,
                "total_engagement": cluster["total_engagement"],
                "velocity": 0.0,
                "growth_rate": 0.0,
                "subreddit_spread": len(cluster["subreddits"]),
                "participating_subs": cluster["subreddits"],
                "post_count": len(cluster["posts"]),
                "first_seen": now,
                "last_updated": now,
                "last_active": now,
            }

            self.db.table("narratives").insert(row).execute()

            # Link all posts to this narrative
            post_ids = [p.get("reddit_id") for p in cluster["posts"] if p.get("reddit_id")]
            if post_ids:
                self.db.table("raw_posts") \
                    .update({"story_id": narrative_id}) \
                    .in_("reddit_id", post_ids) \
                    .execute()

            logger.debug(f"Created narrative: {narrative_id[:8]}... — {cluster['representative_title'][:60]}")
            return narrative_id

        except Exception as e:
            logger.error(f"Error creating narrative: {e}")
            return None

    def update_narrative(self, narrative_id: str, cluster: dict):
        """Update an existing narrative with new cluster data."""
        try:
            now = datetime.now(timezone.utc).isoformat()

            # Get all post IDs already linked
            existing = self.db.table("raw_posts") \
                .select("reddit_id") \
                .eq("story_id", narrative_id) \
                .execute()
            existing_ids = {r["reddit_id"] for r in (existing.data or [])}

            # Find new posts to add
            new_posts = [
                p for p in cluster["posts"]
                if p.get("reddit_id") not in existing_ids
            ]

            if new_posts:
                new_ids = [p["reddit_id"] for p in new_posts if p.get("reddit_id")]
                self.db.table("raw_posts") \
                    .update({"story_id": narrative_id}) \
                    .in_("reddit_id", new_ids) \
                    .execute()

            # Update narrative stats
            self.db.table("narratives").update({
                "total_engagement": cluster["total_engagement"],
                "subreddit_spread": len(cluster["subreddits"]),
                "participating_subs": cluster["subreddits"],
                "post_count": len(cluster["posts"]),
                "last_updated": now,
                "last_active": now,
            }).eq("id", narrative_id).execute()

            logger.debug(f"Updated narrative {narrative_id[:8]}... +{len(new_posts)} posts")

        except Exception as e:
            logger.error(f"Error updating narrative {narrative_id}: {e}")

    def save_clusters(self, clusters: list[dict]) -> tuple[int, int]:
        """
        Save all clusters. Creates new or updates existing narratives.
        Returns (created, updated).
        """
        created = 0
        updated = 0

        for cluster in clusters:
            existing = self._find_existing_narrative(cluster)
            if existing:
                self.update_narrative(existing["id"], cluster)
                updated += 1
            else:
                result = self.create_narrative(cluster)
                if result:
                    created += 1

        logger.info(f"Narratives: {created} created, {updated} updated")
        return created, updated

    def get_active_narratives(self, limit: int = 50) -> list[dict]:
        """Get all active/emerging narratives for the feed."""
        try:
            result = self.db.table("narratives") \
                .select("*") \
                .in_("status", ["emerging", "active"]) \
                .order("narrative_score", desc=True) \
                .limit(limit) \
                .execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error fetching active narratives: {e}")
            return []
