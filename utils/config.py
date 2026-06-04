import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Supabase
    SUPABASE_URL        = os.getenv("SUPABASE_URL")
    SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

    # AI APIs
    GROQ_API_KEY   = os.getenv("GROQ_API_KEY")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

    # Collector
    POLL_INTERVAL_MINUTES = int(os.getenv("POLL_INTERVAL_MINUTES", 10))
    MIN_UPVOTES           = int(os.getenv("MIN_UPVOTES", 50))
    MIN_COMMENTS          = int(os.getenv("MIN_COMMENTS", 30))
    MAX_POST_AGE_HOURS    = int(os.getenv("MAX_POST_AGE_HOURS", 6))

    # Reddit (for when API is approved)
    REDDIT_USER_AGENT    = os.getenv("REDDIT_USER_AGENT", "web:spilled-engine:v1.0")
    REDDIT_REQUEST_DELAY = 2.0
    REDDIT_MAX_RETRIES   = 3

    # Scoring thresholds
    EMERGING_THRESHOLD = 68
    BOILING_THRESHOLD  = 82
    COOLING_THRESHOLD  = 55

    # Lifecycle
    COOLING_NO_ACTIVITY_HOURS    = 12
    ARCHIVE_AFTER_COOLING_HOURS  = 6
    HARD_ARCHIVE_HOURS           = 72

    # Blacklisted keywords
    BLACKLISTED_KEYWORDS = [
        "daily thread", "weekly thread", "megathread",
        "ama", "ask me anything", "mod post",
        "[meta]", "[mod]", "[weekly]", "[daily]",
    ]

    # Subreddits (for when Reddit API approved)
    SUBREDDITS = []
    GLOBAL_ENDPOINTS = []

config = Config()
