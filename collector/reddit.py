"""
Multi-source collector using RSS feeds from sites that don't block cloud IPs.
Sources: TMZ, PageSix, Variety, Billboard, TechCrunch, The Verge, ESPN, etc.
Reddit is replaced until API approval comes through.
"""
import time
import hashlib
import re
from datetime import datetime, timezone
from typing import Optional
import httpx
from loguru import logger
from utils.config import config


RSS_SOURCES = [
    # Celebrity & gossip
    ("https://www.tmz.com/rss.xml",                                    "celebrity",  "TMZ"),
    ("https://pagesix.com/feed/",                                      "celebrity",  "Page Six"),
    ("https://www.justjared.com/feed/",                                "celebrity",  "Just Jared"),
    ("https://www.eonline.com/syndication/feeds/rssfeeds/topstories.xml","celebrity", "E! News"),
    ("https://www.usmagazine.com/feed/",                               "celebrity",  "US Magazine"),

    # Music drama
    ("https://www.billboard.com/feed/",                                "music",      "Billboard"),
    ("https://pitchfork.com/rss/news/feed.xml",                        "music",      "Pitchfork"),
    ("https://consequenceofsound.net/feed/",                           "music",      "Consequence"),

    # Tech drama
    ("https://techcrunch.com/feed/",                                   "tech",       "TechCrunch"),
    ("https://www.theverge.com/rss/index.xml",                         "tech",       "The Verge"),
    ("https://feeds.arstechnica.com/arstechnica/index",                "tech",       "Ars Technica"),
    ("https://www.wired.com/feed/rss",                                 "tech",       "Wired"),

    # Business & finance
    ("https://feeds.bloomberg.com/markets/news.rss",                   "finance",    "Bloomberg"),
    ("https://www.businessinsider.com/rss",                            "finance",    "Business Insider"),
    ("https://fortune.com/feed/",                                      "finance",    "Fortune"),

    # Sports tea
    ("https://www.espn.com/espn/rss/news",                             "sports",     "ESPN"),
    ("https://sports.yahoo.com/rss/",                                  "sports",     "Yahoo Sports"),

    # Viral & internet culture
    ("https://www.buzzfeed.com/index.xml",                             "viral",      "BuzzFeed"),
    ("https://knowyourmeme.com/newsfeed.rss",                          "viral",      "KnowYourMeme"),
    ("https://www.complex.com/rss",                                    "viral",      "Complex"),

    # News & politics
    ("https://feeds.npr.org/1001/rss.xml",                             "politics",   "NPR"),
    ("https://rss.politico.com/politico/rss/politicopicks.xml",        "politics",   "Politico"),

    # Creator & YouTube culture
    ("https://www.tubefilter.com/feed/",                               "creators",   "Tubefilter"),
    ("https://www.thewrap.com/feed/",                                  "creators",   "The Wrap"),

    # Gaming
    ("https://www.ign.com/articles/feed.atom",                         "gaming",     "IGN"),
    ("https://kotaku.com/rss",                                         "gaming",     "Kotaku"),
]


class RedditCollector:
    """
    Renamed but actually an RSS collector now.
    Using RSS from major sites — no IP blocks, completely free.
    """
    def __init__(self):
        self.client = httpx.Client(
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; SpilledBot/1.0)",
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
            },
            timeout=12.0,
            follow_redirects=True,
        )
        self.last_request_time = 0

    def _rate_limit(self):
        elapsed = time.time() - self.last_request_time
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        self.last_request_time = time.time()

    def _clean(self, text: str) -> str:
        text = re.sub(r'<[^>]+>', '', text or '')
        text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>') \
                   .replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' ') \
                   .replace('&hellip;', '...').replace('&#8230;', '...')
        return re.sub(r'\s+', ' ', text).strip()

    def _parse_feed(self, xml: str, source_name: str, category: str) -> list[dict]:
        posts = []
        try:
            # Try Atom entries first, then RSS items
            entries = re.findall(r'<entry>(.*?)</entry>', xml, re.DOTALL)
            if not entries:
                entries = re.findall(r'<item>(.*?)</item>', xml, re.DOTALL)
            if not entries:
                return []

            for entry in entries[:15]:  # max 15 per source
                # Title
                title_m = re.search(r'<title[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', entry, re.DOTALL)
                if not title_m:
                    continue
                title = self._clean(title_m.group(1))
                if not title or len(title) < 15:
                    continue

                # Skip blacklisted keywords
                if any(kw in title.lower() for kw in config.BLACKLISTED_KEYWORDS):
                    continue

                # Link
                link_m = re.search(r'<link[^>]*href=["\']([^"\']+)["\']', entry)
                if not link_m:
                    link_m = re.search(r'<link[^>]*>([^<]+)</link>', entry)
                link = link_m.group(1).strip() if link_m else ""

                # Published date
                date_m = re.search(r'<(?:pubDate|published|updated|dc:date)[^>]*>(.*?)</(?:pubDate|published|updated|dc:date)>', entry, re.DOTALL)
                pub_date = date_m.group(1).strip() if date_m else ""
                try:
                    if pub_date:
                        # Handle various date formats
                        from email.utils import parsedate_to_datetime
                        try:
                            created = parsedate_to_datetime(pub_date)
                        except Exception:
                            created = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
                    else:
                        created = datetime.now(timezone.utc)

                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)

                    age_hours = (datetime.now(timezone.utc) - created).total_seconds() / 3600
                    if age_hours > config.MAX_POST_AGE_HOURS:
                        continue
                except Exception:
                    created = datetime.now(timezone.utc)

                # Description/summary
                desc_m = re.search(r'<(?:description|summary|content)[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</(?:description|summary|content)>', entry, re.DOTALL)
                desc = self._clean(desc_m.group(1))[:400] if desc_m else ""

                post_id = hashlib.md5((title + link).encode()).hexdigest()[:12]

                posts.append({
                    "id":           post_id,
                    "reddit_id":    post_id,
                    "title":        title[:500],
                    "selftext":     desc,
                    "author":       source_name,
                    "subreddit":    source_name.lower().replace(" ", "_"),
                    "score":        100,
                    "num_comments": 30,
                    "upvote_ratio": 0.9,
                    "created_utc":  created.isoformat(),
                    "permalink":    link,
                    "url":          link,
                    "is_self":      True,
                    "flair":        "",
                    "engagement":   160,
                    "content_hash": hashlib.md5(title.lower().encode()).hexdigest(),
                    "category":     category,
                    "source_name":  source_name,
                })
        except Exception as e:
            logger.error(f"Parse error for {source_name}: {e}")
        return posts

    def _fetch_source(self, url: str, category: str, source_name: str) -> list[dict]:
        self._rate_limit()
        try:
            resp = self.client.get(url, timeout=10.0)
            if resp.status_code in (403, 404, 429):
                logger.warning(f"HTTP {resp.status_code} on {source_name}")
                return []
            resp.raise_for_status()
            posts = self._parse_feed(resp.text, source_name, category)
            logger.debug(f"{source_name}: {len(posts)} posts")
            return posts
        except Exception as e:
            logger.warning(f"Failed {source_name}: {e}")
            return []

    def collect_all(self) -> list[dict]:
        all_posts = {}
        total = 0

        for url, category, name in RSS_SOURCES:
            posts = self._fetch_source(url, category, name)
            for p in posts:
                all_posts[p["id"]] = p
            total += len(posts)

        deduped = list(all_posts.values())
        logger.info(f"Collection complete: {total} fetched, {len(deduped)} unique posts")
        return deduped

    def close(self):
        self.client.close()
                                 
