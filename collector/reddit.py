"""
RSS-based collector — uses Reddit RSS feeds which work from any IP.
Reddit blocks cloud provider IPs on JSON endpoints but RSS works fine.
"""
import time
import hashlib
from datetime import datetime, timezone
from typing import Optional
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from loguru import logger
from utils.config import config

# Reddit RSS feeds — these work from cloud IPs
RSS_SUBREDDITS = [
    # Tech & AI
    ("technology",        "tech"),
    ("artificial",        "tech"),
    ("MachineLearning",   "tech"),
    ("OpenAI",            "tech"),
    ("programming",       "tech"),
    ("startups",          "tech"),
    # Creators & culture
    ("NewTubers",         "creators"),
    ("youtubers",         "creators"),
    ("TikTokCringe",      "viral"),
    ("BeautyGuruChatter", "celebrity"),
    ("influencersnark",   "celebrity"),
    ("popculturechat",    "celebrity"),
    # Celebrity & gossip
    ("Fauxmoi",           "celebrity"),
    ("popheads",          "music"),
    ("entertainment",     "celebrity"),
    # Business & finance
    ("wallstreetbets",    "finance"),
    ("investing",         "finance"),
    ("business",          "finance"),
    # Sports
    ("nba",               "sports"),
    ("soccer",            "sports"),
    ("nfl",               "sports"),
    # Viral & internet
    ("PublicFreakout",    "viral"),
    ("interestingasfuck", "viral"),
    ("OutOfTheLoop",      "viral"),
    # News
    ("worldnews",         "politics"),
    ("news",              "politics"),
    # Entertainment
    ("gaming",            "gaming"),
    ("movies",            "celebrity"),
    ("television",        "celebrity"),
]

GLOBAL_RSS = [
    ("https://www.reddit.com/r/all/hot.rss",     "viral"),
    ("https://www.reddit.com/r/popular/hot.rss", "viral"),
]

class RedditCollector:
    def __init__(self):
        self.client = httpx.Client(
            headers={
                "User-Agent": config.REDDIT_USER_AGENT,
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
            },
            timeout=15.0,
            follow_redirects=True,
        )
        self.last_request_time = 0

    def _rate_limit(self):
        elapsed = time.time() - self.last_request_time
        if elapsed < config.REDDIT_REQUEST_DELAY:
            time.sleep(config.REDDIT_REQUEST_DELAY - elapsed)
        self.last_request_time = time.time()

    def _parse_rss(self, xml: str, subreddit: str, category: str) -> list[dict]:
        """Parse Reddit RSS XML into post dicts."""
        posts = []
        try:
            import re
            entries = re.findall(r'<entry>(.*?)</entry>', xml, re.DOTALL)
            for entry in entries:
                title_m = re.search(r'<title[^>]*>(.*?)</title>', entry, re.DOTALL)
                link_m  = re.search(r'<link[^>]*href=["\']([^"\']+)["\']', entry)
                author_m= re.search(r'<name>(.*?)</name>', entry, re.DOTALL)
                time_m  = re.search(r'<updated>(.*?)</updated>', entry, re.DOTALL)
                content_m = re.search(r'<content[^>]*>(.*?)</content>', entry, re.DOTALL)

                if not title_m or not link_m:
                    continue

                title = self._clean(title_m.group(1))
                if not title or len(title) < 10:
                    continue

                # Skip blacklisted keywords
                if any(kw in title.lower() for kw in config.BLACKLISTED_KEYWORDS):
                    continue

                link = link_m.group(1)
                author = self._clean(author_m.group(1)) if author_m else "unknown"
                updated = time_m.group(1).strip() if time_m else datetime.now(timezone.utc).isoformat()
                content = self._clean(content_m.group(1))[:500] if content_m else ""

                # Parse time
                try:
                    created = datetime.fromisoformat(updated.replace('Z', '+00:00'))
                    age_hours = (datetime.now(timezone.utc) - created).total_seconds() / 3600
                    if age_hours > config.MAX_POST_AGE_HOURS:
                        continue
                except Exception:
                    created = datetime.now(timezone.utc)

                post_id = hashlib.md5(link.encode()).hexdigest()[:10]

                posts.append({
                    "id":           post_id,
                    "reddit_id":    post_id,
                    "title":        title[:500],
                    "selftext":     content,
                    "author":       author,
                    "subreddit":    subreddit,
                    "score":        100,       # RSS doesn't expose score
                    "num_comments": 50,        # RSS doesn't expose comments
                    "upvote_ratio": 0.9,
                    "created_utc":  created.isoformat(),
                    "permalink":    link,
                    "url":          link,
                    "is_self":      True,
                    "flair":        "",
                    "engagement":   200,       # default
                    "content_hash": hashlib.md5(title.lower().encode()).hexdigest(),
                    "category":     category,
                })
        except Exception as e:
            logger.error(f"RSS parse error for r/{subreddit}: {e}")
        return posts

    def _clean(self, text: str) -> str:
        import re
        text = re.sub(r'<[^>]+>', '', text)
        text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' ')
        return text.strip()

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(min=2, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        reraise=False,
    )
    def _fetch_rss(self, url: str, subreddit: str, category: str) -> list[dict]:
        self._rate_limit()
        try:
            resp = self.client.get(url, timeout=12.0)
            if resp.status_code == 429:
                logger.warning(f"Rate limited on {url}")
                time.sleep(30)
                return []
            if resp.status_code in (403, 404):
                logger.warning(f"HTTP {resp.status_code} on {url}")
                return []
            resp.raise_for_status()
            posts = self._parse_rss(resp.text, subreddit, category)
            logger.debug(f"r/{subreddit}: {len(posts)} posts via RSS")
            return posts
        except Exception as e:
            logger.warning(f"Failed r/{subreddit}: {e}")
            return []

    def collect_all(self) -> list[dict]:
        all_posts = {}

        # Global feeds
        for url, category in GLOBAL_RSS:
            posts = self._fetch_rss(url, "all", category)
            for p in posts:
                all_posts[p["id"]] = p

        # Subreddit feeds
        for subreddit, category in RSS_SUBREDDITS:
            url = f"https://www.reddit.com/r/{subreddit}/hot.rss?limit=25"
            posts = self._fetch_rss(url, subreddit, category)
            for p in posts:
                all_posts[p["id"]] = p

        deduped = list(all_posts.values())
        logger.info(f"Collection complete: {len(deduped)} unique posts via RSS")
        return deduped

    def close(self):
        self.client.close()
                   
