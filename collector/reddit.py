import time
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from loguru import logger
from utils.config import config


class RedditCollector:
    def __init__(self):
        self.client = httpx.Client(
            headers={"User-Agent": config.REDDIT_USER_AGENT},
            timeout=15.0,
            follow_redirects=True,
        )
        self.last_request_time = 0

    def _rate_limit(self):
        """Enforce minimum delay between requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < config.REDDIT_REQUEST_DELAY:
            time.sleep(config.REDDIT_REQUEST_DELAY - elapsed)
        self.last_request_time = time.time()

    @retry(
        stop=stop_after_attempt(config.REDDIT_MAX_RETRIES),
        wait=wait_exponential(multiplier=config.REDDIT_BACKOFF_BASE, min=2, max=30),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        reraise=True,
    )
    def _fetch(self, endpoint: str, params: dict = None) -> Optional[dict]:
        """Fetch a Reddit JSON endpoint with rate limiting and retries."""
        self._rate_limit()
        url = f"{config.REDDIT_BASE_URL}{endpoint}"
        try:
            resp = self.client.get(url, params=params or {"limit": 100, "raw_json": 1})
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 60))
                logger.warning(f"Rate limited by Reddit. Waiting {retry_after}s")
                time.sleep(retry_after)
                raise httpx.HTTPStatusError("Rate limited", request=resp.request, response=resp)
            if resp.status_code == 403:
                logger.warning(f"403 on {endpoint} — subreddit may be private/banned")
                return None
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            logger.warning(f"Timeout fetching {endpoint}")
            raise

    def _is_valid_post(self, post: dict) -> bool:
        """Filter out low quality posts."""
        # Basic thresholds
        if post.get("score", 0) < config.MIN_UPVOTES and post.get("num_comments", 0) < config.MIN_COMMENTS:
            return False

        # Age check
        created = datetime.fromtimestamp(post.get("created_utc", 0), tz=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - created).total_seconds() / 3600
        if age_hours > config.MAX_POST_AGE_HOURS:
            return False

        # NSFW filter
        if post.get("over_18", False):
            return False

        # Blacklisted subreddit
        if post.get("subreddit", "").lower() in {s.lower() for s in config.BLACKLISTED_SUBREDDITS}:
            return False

        # Blacklisted keywords in title
        title_lower = post.get("title", "").lower()
        if any(kw in title_lower for kw in config.BLACKLISTED_KEYWORDS):
            return False

        # Skip pure image/video posts with no text context
        if post.get("is_video", False) and not post.get("selftext"):
            pass  # Allow videos from good subreddits

        return True

    def _normalize_post(self, post: dict) -> dict:
        """Normalize a Reddit post into our schema."""
        return {
            "id": post["id"],
            "title": post.get("title", "")[:500],
            "selftext": (post.get("selftext", "") or "")[:2000],
            "author": post.get("author", "[deleted]"),
            "subreddit": post.get("subreddit", ""),
            "score": post.get("score", 0),
            "num_comments": post.get("num_comments", 0),
            "upvote_ratio": post.get("upvote_ratio", 0.5),
            "created_utc": datetime.fromtimestamp(
                post.get("created_utc", 0), tz=timezone.utc
            ).isoformat(),
            "permalink": f"https://reddit.com{post.get('permalink', '')}",
            "url": post.get("url", ""),
            "is_self": post.get("is_self", True),
            "flair": post.get("link_flair_text", ""),
            # Computed
            "engagement": post.get("score", 0) + (post.get("num_comments", 0) * 2),
            "content_hash": hashlib.md5(
                post.get("title", "").lower().encode()
            ).hexdigest(),
        }

    def fetch_subreddit(self, subreddit: str, sort: str = "new") -> list[dict]:
        """Fetch posts from a single subreddit."""
        endpoint = f"/r/{subreddit}/{sort}.json"
        data = self._fetch(endpoint, {"limit": 50, "raw_json": 1})
        if not data:
            return []

        posts = []
        for child in data.get("data", {}).get("children", []):
            post = child.get("data", {})
            if self._is_valid_post(post):
                posts.append(self._normalize_post(post))

        logger.debug(f"r/{subreddit}: {len(posts)} valid posts")
        return posts

    def fetch_global(self, endpoint: str) -> list[dict]:
        """Fetch from global endpoints like r/all or r/popular."""
        data = self._fetch(endpoint, {"limit": 100, "raw_json": 1})
        if not data:
            return []

        posts = []
        for child in data.get("data", {}).get("children", []):
            post = child.get("data", {})
            if self._is_valid_post(post):
                posts.append(self._normalize_post(post))

        logger.debug(f"{endpoint}: {len(posts)} valid posts")
        return posts

    def collect_all(self) -> list[dict]:
        """
        Full collection run — global feeds + all subreddits.
        Returns deduplicated list of valid posts.
        """
        all_posts = {}
        total_fetched = 0

        # Global feeds first
        for endpoint in config.GLOBAL_ENDPOINTS:
            try:
                posts = self.fetch_global(endpoint)
                for p in posts:
                    all_posts[p["id"]] = p
                total_fetched += len(posts)
            except Exception as e:
                logger.error(f"Failed fetching {endpoint}: {e}")

        # Individual subreddits
        for subreddit in config.SUBREDDITS:
            try:
                posts = self.fetch_subreddit(subreddit)
                for p in posts:
                    all_posts[p["id"]] = p
                total_fetched += len(posts)
            except Exception as e:
                logger.error(f"Failed fetching r/{subreddit}: {e}")

        deduped = list(all_posts.values())
        logger.info(f"Collection complete: {total_fetched} fetched, {len(deduped)} unique valid posts")
        return deduped

    def close(self):
        self.client.close()
