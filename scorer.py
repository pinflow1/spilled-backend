"""
Narrative Scoring Engine
Scores narratives 0-100 based on velocity, growth, engagement,
subreddit spread, freshness, and coverage gap.
"""
from datetime import datetime, timezone, timedelta
from loguru import logger
from utils.db import get_db
from utils.config import config


class NarrativeScorer:
    def __init__(self):
        self.db = get_db()

    def _normalize(self, value: float, min_val: float, max_val: float) -> float:
        """Normalize a value to 0-1 range."""
        if max_val <= min_val:
            return 0.0
        return max(0.0, min(1.0, (value - min_val) / (max_val - min_val)))

    def _score_velocity(self, narrative: dict, posts: list[dict]) -> float:
        """Score based on engagement per minute."""
        try:
            first_seen = datetime.fromisoformat(narrative["first_seen"])
            now = datetime.now(timezone.utc)
            minutes = max((now - first_seen).total_seconds() / 60, 1)
            velocity = narrative["total_engagement"] / minutes
            return self._normalize(velocity, 0, 500) * 100
        except Exception:
            return 0.0

    def _score_growth_rate(self, narrative_id: str, current_engagement: int) -> float:
        """Score based on growth vs 30 minutes ago."""
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
            result = self.db.table("narratives") \
                .select("total_engagement") \
                .eq("id", narrative_id) \
                .lte("last_updated", cutoff) \
                .limit(1) \
                .execute()

            if not result.data:
                return 30.0  # assume growing if no history

            past = result.data[0]["total_engagement"]
            growth = (current_engagement - past) / max(past, 1)
            return self._normalize(growth, 0, 3.0) * 100
        except Exception:
            return 0.0

    def _score_engagement(self, total_engagement: int) -> float:
        """Score raw engagement volume."""
        return self._normalize(total_engagement, 100, 50000) * 100

    def _score_subreddit_spread(self, spread: int) -> float:
        """Score community diversity — more subreddits = more narrative weight."""
        return self._normalize(spread, 1, 10) * 100

    def _score_freshness(self, first_seen_iso: str) -> float:
        """Score recency — newer stories score higher."""
        try:
            first_seen = datetime.fromisoformat(first_seen_iso)
            age_hours = (datetime.now(timezone.utc) - first_seen).total_seconds() / 3600
            # Full score if < 2h, linear decay to 0 at 24h
            return max(0.0, self._normalize(24 - age_hours, 0, 22) * 100)
        except Exception:
            return 0.0

    def _score_coverage_gap(self, narrative: dict) -> float:
        """
        Score opportunity based on how underreported the story is.
        High engagement + few subreddits = early opportunity.
        High engagement + many subreddits = later stage.
        This is a proxy until we add YouTube/Google checks.
        """
        engagement = narrative.get("total_engagement", 0)
        spread = narrative.get("subreddit_spread", 1)
        post_count = narrative.get("post_count", 1)

        # High engagement with low spread = big opportunity
        if spread <= 2 and engagement > 500:
            return 85.0
        if spread <= 3 and engagement > 1000:
            return 70.0
        if spread <= 5 and engagement > 2000:
            return 55.0
        return max(0.0, 40.0 - (spread * 3))

    def calculate_score(self, narrative: dict, posts: list[dict] = None) -> dict:
        """
        Calculate full narrative score.
        Returns dict with total score and component breakdown.
        """
        posts = posts or []

        v_score  = self._score_velocity(narrative, posts)
        g_score  = self._score_growth_rate(narrative["id"], narrative["total_engagement"])
        e_score  = self._score_engagement(narrative["total_engagement"])
        s_score  = self._score_subreddit_spread(narrative.get("subreddit_spread", 1))
        f_score  = self._score_freshness(narrative["first_seen"])
        c_score  = self._score_coverage_gap(narrative)

        # Weighted total
        total = (
            v_score  * 0.25 +
            g_score  * 0.22 +
            e_score  * 0.15 +
            s_score  * 0.23 +
            f_score  * 0.15
        )

        return {
            "narrative_score":    round(total, 2),
            "opportunity_score":  round(c_score, 2),
            "velocity":           round(v_score, 2),
            "growth_rate":        round(g_score, 2),
            "components": {
                "velocity":    round(v_score, 2),
                "growth":      round(g_score, 2),
                "engagement":  round(e_score, 2),
                "spread":      round(s_score, 2),
                "freshness":   round(f_score, 2),
                "coverage_gap": round(c_score, 2),
            }
        }

    def get_status(self, score: float, narrative: dict) -> str:
        """Determine narrative status from score and age."""
        try:
            last_active = datetime.fromisoformat(narrative.get("last_active", narrative["first_seen"]))
            hours_inactive = (datetime.now(timezone.utc) - last_active).total_seconds() / 3600

            if hours_inactive > config.COOLING_NO_ACTIVITY_HOURS:
                return "cooling"
            if score < config.COOLING_THRESHOLD:
                return "cooling"
            if score >= config.BOILING_THRESHOLD:
                return "active"
            if score >= config.EMERGING_THRESHOLD:
                return "emerging"
            return "cooling"
        except Exception:
            return "emerging"

    def score_all_narratives(self) -> int:
        """Score all active narratives. Returns count updated."""
        try:
            result = self.db.table("narratives") \
                .select("*") \
                .in_("status", ["emerging", "active"]) \
                .execute()

            narratives = result.data or []
            if not narratives:
                logger.info("No active narratives to score")
                return 0

            updated = 0
            for narrative in narratives:
                scores = self.calculate_score(narrative)
                status = self.get_status(scores["narrative_score"], narrative)

                self.db.table("narratives").update({
                    "narrative_score":  scores["narrative_score"],
                    "opportunity_score": scores["opportunity_score"],
                    "velocity":         scores["velocity"],
                    "growth_rate":      scores["growth_rate"],
                    "status":           status,
                    "last_updated":     datetime.now(timezone.utc).isoformat(),
                }).eq("id", narrative["id"]).execute()

                updated += 1

            logger.info(f"Scored {updated} narratives")
            return updated

        except Exception as e:
            logger.error(f"Error scoring narratives: {e}")
            return 0
