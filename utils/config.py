import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Supabase
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

    # AI APIs
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

    # Collector settings
    POLL_INTERVAL_MINUTES = int(os.getenv("POLL_INTERVAL_MINUTES", 10))
    MIN_UPVOTES = int(os.getenv("MIN_UPVOTES", 50))
    MIN_COMMENTS = int(os.getenv("MIN_COMMENTS", 30))
    MAX_POST_AGE_HOURS = int(os.getenv("MAX_POST_AGE_HOURS", 6))

    # Reddit
    REDDIT_USER_AGENT = "Spilled:v1.0 (narrative intelligence platform)"
    REDDIT_BASE_URL = "https://www.reddit.com"
    REDDIT_REQUEST_DELAY = 2.0      # seconds between requests
    REDDIT_BACKOFF_BASE = 2         # exponential backoff base
    REDDIT_MAX_RETRIES = 3

    # Scoring thresholds
    EMERGING_THRESHOLD = 68
    BOILING_THRESHOLD = 82
    COOLING_THRESHOLD = 55

    # Story lifecycle
    COOLING_NO_GROWTH_HOURS = 4
    COOLING_NO_ACTIVITY_HOURS = 12
    ARCHIVE_AFTER_COOLING_HOURS = 6
    HARD_ARCHIVE_HOURS = 72

    # Subreddits to monitor — curated for Spilled's audience
    SUBREDDITS = [
        # Tech & AI drama
        "technology", "artificial", "MachineLearning", "OpenAI",
        "programming", "webdev", "startups", "Entrepreneur",

        # Creator & internet culture
        "NewTubers", "youtubers", "TikTokCringe", "BeautyGuruChatter",
        "influencersnark", "popculturechat",

        # Celebrity & gossip
        "Fauxmoi", "popheads", "entertainment", "Music",

        # Business & finance drama
        "wallstreetbets", "investing", "Economics", "business",

        # Sports tea
        "nba", "soccer", "nfl", "sports",

        # Viral & internet
        "PublicFreakout", "interestingasfuck", "mildlyinteresting",
        "todayilearned", "OutOfTheLoop",

        # News & politics (curated)
        "worldnews", "news",

        # Niche communities
        "gaming", "pcgaming", "movies", "television",
        "science", "space",
    ]

    # Global feed endpoints
    GLOBAL_ENDPOINTS = [
        "/r/all/new.json",
        "/r/popular.json",
    ]

    # Blacklisted subreddits (low quality / noise)
    BLACKLISTED_SUBREDDITS = {
        "memes", "funny", "dankmemes", "me_irl", "shitposting",
        "teenagers", "AskReddit", "tifu", "confession",
        "politics", "Conservative", "Liberal", "политика",
    }

    # Blacklisted keywords (filter out noise)
    BLACKLISTED_KEYWORDS = [
        "daily thread", "weekly thread", "megathread",
        "ama", "ask me anything", "mod post",
        "[meta]", "[mod]", "[weekly]", "[daily]",
    ]

config = Config()
